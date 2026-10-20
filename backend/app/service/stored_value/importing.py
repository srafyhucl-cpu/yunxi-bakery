"""有赞储值余额期初导入服务（CSV -> 校验 -> 入账 -> 对账 -> 回滚）。

本服务只处理「期初导入」语义：把有赞侧门店存量储值余额一次性搬到本地
member_balance / balance_ledger，作为后续本地交易期初数；不接触真实有赞 API、
不接触生产库。入账统一走 MemberBalanceService.credit（biz_type=recharge、
source=import），绝不直接 UPDATE member_balance，保证账务拆分与幂等合同一致。

批次状态机：created -> validated -> applied / failed，回滚后 rolled_back。
行状态机：valid / invalid / conflict -> applied，回滚后 rolled_back。
"""

import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from app.logger import setup_logger
from app.models.customer_master import (
    CustomerIdentityConfidence,
    CustomerIdentityLinkCreate,
    CustomerIdentityType,
    CustomerIdentityVerificationStatus,
    CustomerMasterCreate,
    CustomerSourceSystem,
)
from app.models.stored_value import BalanceBizType, BalanceSource
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.youzan_stored_value_import_repo import YouzanStoredValueImportRepo
from app.service.stored_value.member import DEFAULT_TENANT_ID, MemberBalanceService

logger = setup_logger()

# 手机号规则与既有认领链路保持一致：11 位、1 开头
MOBILE_PATTERN = re.compile(r"^1\d{10}$")
MOBILE_MASKED_HEAD = 3
MOBILE_MASKED_TAIL = 4
BATCH_ID_PREFIX = "ysv_"
BATCH_ID_TIME_FORMAT = "%Y%m%d%H%M%S"

# 批次状态
BATCH_STATUS_CREATED = "created"
BATCH_STATUS_VALIDATED = "validated"
BATCH_STATUS_APPLIED = "applied"
BATCH_STATUS_FAILED = "failed"
BATCH_STATUS_ROLLED_BACK = "rolled_back"

# 行状态
ROW_STATUS_VALID = "valid"
ROW_STATUS_INVALID = "invalid"
ROW_STATUS_CONFLICT = "conflict"
ROW_STATUS_APPLIED = "applied"
ROW_STATUS_ROLLED_BACK = "rolled_back"

# 可复用批次状态：created / validated 可复用；applied 直接返回（幂等，不重复入账）；
# failed / rolled_back 必须新建批次，避免一次批次记录被 applied->rolled_back->applied
# 反复改写而覆盖审计链。
REUSABLE_BATCH_STATUSES = frozenset(
    {BATCH_STATUS_CREATED, BATCH_STATUS_VALIDATED, BATCH_STATUS_APPLIED}
)

# 期初导入入账语义：期初导入说明
APPLY_NOTE = "期初导入：有赞存量储值余额一次性入账"
ROLLBACK_NOTE = "期初导入回滚：撤销本批次入账金额"

# 表头别名 -> (规范字段名, 该列金额单位是否为「元」)
# 英文 *_fen 列一律按「分」整数读取；中文金额列表头按「元」十进制换算成分，
# 便于真实有赞门店导出文件直接复用同一脚本。
HEADER_SPECS: dict[str, tuple[str, bool]] = {
    "mobile": ("mobile", False),
    "手机号": ("mobile", False),
    "会员手机号": ("mobile", False),
    "客户手机号": ("mobile", False),
    "display_name": ("display_name", False),
    "会员昵称": ("display_name", False),
    "客户姓名": ("display_name", False),
    "客户昵称": ("display_name", False),
    "principal_fen": ("principal_fen", False),
    "本金(分)": ("principal_fen", False),
    "本金": ("principal_fen", True),
    "实充本金": ("principal_fen", True),
    "bonus_fen": ("bonus_fen", False),
    "赠送金(分)": ("bonus_fen", False),
    "赠送金": ("bonus_fen", True),
    "赠送余额": ("bonus_fen", True),
    "reported_total_fen": ("reported_total_fen", False),
    "储值余额(分)": ("reported_total_fen", False),
    "储值余额": ("reported_total_fen", True),
    "客户储值余额": ("reported_total_fen", True),
    "yz_open_id": ("yz_open_id", False),
    "有赞open_id": ("yz_open_id", False),
    "card_no": ("card_no", False),
    "会员卡号": ("card_no", False),
    "card_alias": ("card_alias", False),
    "会员卡名称": ("card_alias", False),
    "权益卡": ("card_alias", False),
}

# 必填表头（其余列缺省即按空值/0 处理）
REQUIRED_FIELDS = ("mobile", "principal_fen")


class StoredValueImportError(Exception):
    """导入流程可预期的拒绝：校验失败、入账或回滚被拒。"""


@dataclass(frozen=True)
class StoredValueImportRow:
    """CSV 中的一行储值余额输入（金额单位为「分」，整数）。"""

    row_no: int
    mobile: str
    display_name: str = ""
    principal_fen: int = 0
    bonus_fen: int = 0
    reported_total_fen: int | None = None
    yz_open_id: str = ""
    card_no: str = ""
    card_alias: str = ""


class StoredValueImportService:
    """有赞储值余额期初导入：创建批次、校验、入账、对账与回滚。"""

    def __init__(
        self,
        db,
        tenant_id: str = DEFAULT_TENANT_ID,
        member_service: MemberBalanceService | None = None,
    ) -> None:
        self._db = db
        self._tenant_id = tenant_id
        self._repo = YouzanStoredValueImportRepo(db)
        self._balance_repo = MemberBalanceRepo(db)
        self._ledger_repo = BalanceLedgerRepo(db)
        self._customer_repo = CustomerMasterRepo(db)
        self._member_service = member_service or MemberBalanceService(
            balance_repo=self._balance_repo,
            ledger_repo=self._ledger_repo,
            customer_repo=self._customer_repo,
        )

    async def create_batch_from_csv(self, csv_path: str | Path) -> dict:
        """读取 CSV 创建/复用导期初导入批次，返回批次记录。

        同一文件（sha256 相同）按状态决定复用：created / validated 复用既有
        批次，applied 直接返回原批次（幂等，不重复入账），failed / rolled_back
        一律新建 batch_id，保证每次真实导入尝试都有独立的审计记录；不会出现
        同一批次记录被 applied -> rolled_back -> applied 反复改写的情况。
        金额列必须是「分」整数（或中文「元」列按十进制换算），禁止 float。
        """
        path = Path(csv_path)
        raw_bytes = path.read_bytes()
        digest = hashlib.sha256(raw_bytes).hexdigest()
        existing = await self._repo.get_latest_batch_by_sha256(digest)
        if existing is not None and existing["status"] in REUSABLE_BATCH_STATUSES:
            logger.info(
                "复用已有储值导入批次 batch_id=%s status=%s",
                existing["id"],
                existing["status"],
            )
            return existing
        rows = self._parse_csv(raw_bytes)
        batch_id = self._build_batch_id(digest)
        async with self._repo.transaction():
            await self._repo.create_batch(
                batch_id=batch_id,
                source_file=str(path),
                source_sha256=digest,
                total_rows=len(rows),
            )
            await self._repo.insert_rows(batch_id, rows)
        logger.info("创建储值导入批次 batch_id=%s rows=%s", batch_id, len(rows))
        return await self._require_batch(batch_id)

    async def validate_batch(self, batch_id: str) -> dict:
        """校验批次并落库行状态；返回结构化报告。

        `invalid_rows` 为不可入账行数（含 invalid 与 conflict），只有其为 0
        批次才进入 validated，apply 才会放行。
        """
        batch = await self._require_batch(batch_id)
        if batch["status"] == BATCH_STATUS_APPLIED:
            return await self.report(batch_id)
        async with self._repo.transaction():
            await self._repo.reset_row_statuses(batch_id)
            rows = await self._repo.list_rows(batch_id)
            mobile_counts = Counter(
                str(row["mobile"]) for row in rows if str(row["mobile"])
            )
            valid_rows = 0
            invalid_rows = 0
            total_principal = 0
            total_bonus = 0
            for row in rows:
                status, error = await self._validate_row(row, mobile_counts)
                if status is None:
                    status = ROW_STATUS_VALID
                    valid_rows += 1
                    total_principal += int(row["principal_fen"])
                    total_bonus += int(row["bonus_fen"])
                else:
                    invalid_rows += 1
                await self._repo.update_row_status(
                    int(row["id"]), status=status, error=error
                )
            batch_status = (
                BATCH_STATUS_VALIDATED if invalid_rows == 0 else BATCH_STATUS_FAILED
            )
            await self._repo.update_batch_validation(
                batch_id,
                status=batch_status,
                valid_rows=valid_rows,
                invalid_rows=invalid_rows,
                total_principal_fen=total_principal,
                total_bonus_fen=total_bonus,
                total_stored_value_fen=total_principal + total_bonus,
            )
        logger.info(
            "储值导入批次校验完成 batch_id=%s status=%s valid=%s invalid=%s",
            batch_id,
            batch_status,
            valid_rows,
            invalid_rows,
        )
        return await self.report(batch_id)

    async def apply_batch(self, batch_id: str) -> dict:
        """全有或全无地入账批次；已入账批次直接返回原报告，不重复加款。"""
        batch = await self._require_batch(batch_id)
        if batch["status"] == BATCH_STATUS_APPLIED:
            return await self.report(batch_id)
        if batch["status"] != BATCH_STATUS_VALIDATED or int(batch["invalid_rows"]) != 0:
            raise StoredValueImportError("批次未通过校验或存在冲突，拒绝入账")
        # 阶段一：幂等确保客户主档与手机号身份（独立提交，回滚不删除客户）
        identities: dict[int, str] = {}
        for row in await self._repo.list_rows(batch_id, status=ROW_STATUS_VALID):
            identities[int(row["row_no"])] = await self._ensure_phone_identity(
                str(row["mobile"]), str(row["display_name"])
            )
        # 阶段二：单事务逐行入账，任一行失败整批回滚
        try:
            async with self._repo.transaction():
                applied_rows = 0
                for row in await self._repo.list_rows(
                    batch_id, status=ROW_STATUS_VALID
                ):
                    await self._apply_row(batch_id, row, identities[int(row["row_no"])])
                    applied_rows += 1
                await self._repo.mark_batch_applied(
                    batch_id, applied_rows=applied_rows, note=APPLY_NOTE
                )
        except Exception as exc:
            await self._mark_batch_failed(batch_id, note=f"入账中止：{exc}")
            logger.error(
                "储值期初导入入账失败，已整批回滚 batch_id=%s err=%s", batch_id, exc
            )
            if isinstance(exc, StoredValueImportError):
                raise
            raise StoredValueImportError("批次入账失败，已整批回滚") from exc
        logger.info("储值导入批次入账完成 batch_id=%s", batch_id)
        return await self.report(batch_id)

    async def rollback_batch(self, batch_id: str) -> dict:
        """回滚干净批次：撤销本批次入账金额并删除导入流水，保留客户主档。

        只有「导入后这些会员没有后续流水」的批次才允许回滚；否则拒绝并
        给出不安全的会员脱敏清单，避免撤销已发生消费的期初余额。
        """
        batch = await self._require_batch(batch_id)
        if batch["status"] == BATCH_STATUS_ROLLED_BACK:
            return await self.report(batch_id)
        if batch["status"] != BATCH_STATUS_APPLIED:
            raise StoredValueImportError("只允许回滚已入账批次")
        applied_rows = await self._repo.list_rows(batch_id, status=ROW_STATUS_APPLIED)
        unsafe = await self._find_unsafe_members(batch_id, applied_rows)
        if unsafe:
            detail = "；".join(f"{mask_mobile(m)}（{reason}）" for m, reason in unsafe)
            logger.error("储值导入批次回滚被拒 batch_id=%s unsafe=%s", batch_id, detail)
            raise StoredValueImportError(f"批次已产生后续账务，拒绝回滚：{detail}")
        try:
            async with self._repo.transaction():
                for row in applied_rows:
                    await self._rollback_row(batch_id, row)
                await self._repo.mark_rows_rolled_back(batch_id)
                await self._repo.mark_batch_rolled_back(batch_id, note=ROLLBACK_NOTE)
        except Exception as exc:
            # 回滚失败时事务已整批回滚，账务仍保持入账原状，故不改批次状态，
            # 待运营修复原因（例如余额被外部改写）后可再次尝试回滚。
            logger.error("储值导入批次回滚失败 batch_id=%s err=%s", batch_id, exc)
            raise StoredValueImportError("批次回滚失败，未做任何变更") from exc
        logger.info("储值导入批次回滚完成 batch_id=%s", batch_id)
        return await self.report(batch_id)

    async def report(self, batch_id: str) -> dict:
        """返回结构化报告：总数、金额合计、无效/冲突明细与对账差异。

        对账同时核对总额与本金/赠送金拆分：只比对总额无法证明拆分结构正确，
        故分别给出 principal_variance_fen / bonus_variance_fen。
        """
        batch = await self._require_batch(batch_id)
        rows = await self._repo.list_rows(batch_id)
        invalid_details = self._row_details(rows, ROW_STATUS_INVALID)
        conflict_details = self._row_details(rows, ROW_STATUS_CONFLICT)
        expected_principal = int(batch["total_principal_fen"])
        expected_bonus = int(batch["total_bonus_fen"])
        expected_total = int(batch["total_stored_value_fen"])
        split = await self._ledger_repo.sum_split_by_biz(
            biz_type=BalanceBizType.RECHARGE, biz_id=batch_id
        )
        applied = batch["status"] == BATCH_STATUS_APPLIED
        return {
            "batch_id": batch["id"],
            "source_file": batch["source_file"],
            "source_sha256": batch["source_sha256"],
            "status": batch["status"],
            # 期初导入语义：本批次金额为有赞存量储值余额一次搬入，非当期新增充值
            "scope": "period_initial_import",
            "total_rows": int(batch["total_rows"]),
            "valid_rows": int(batch["valid_rows"]),
            "invalid_rows": int(batch["invalid_rows"]),
            "conflict_rows": len(conflict_details),
            "applied_rows": int(batch["applied_rows"]),
            "expected_principal_fen": expected_principal,
            "expected_bonus_fen": expected_bonus,
            "expected_total_fen": expected_total,
            "applied_principal_fen": split["principal_fen"],
            "applied_bonus_fen": split["bonus_fen"],
            "applied_total_fen": split["total_fen"],
            "principal_variance_fen": (expected_principal - split["principal_fen"])
            if applied
            else 0,
            "bonus_variance_fen": (expected_bonus - split["bonus_fen"])
            if applied
            else 0,
            "variance_fen": (expected_total - split["total_fen"]) if applied else 0,
            "invalid_details": invalid_details,
            "conflict_details": conflict_details,
            "created_at": batch["created_at"],
            "applied_at": batch["applied_at"],
            "rolled_back_at": batch["rolled_back_at"],
            "note": batch["note"],
        }

    async def _apply_row(self, batch_id: str, row: dict, customer_id: str) -> None:
        """入账单行：先补身份快照再走 credit，绝不直接改余额。"""
        mobile = str(row["mobile"])
        bonus_fen = int(row["bonus_fen"])
        principal_fen = int(row["principal_fen"])
        await self._balance_repo.upsert_identity(
            mobile=mobile,
            customer_id=customer_id,
            yz_open_id=str(row["yz_open_id"]),
            display_name=str(row["display_name"]),
            is_member=1,
            card_alias=str(row["card_alias"]),
            card_no=str(row["card_no"]),
        )
        if await self._balance_repo.get_stored_value_fen(mobile) != 0:
            raise StoredValueImportError(f"会员 {mask_mobile(mobile)} 本地已有非零余额")
        await self._member_service.credit(
            user_id=customer_id,
            mobile=mobile,
            amount_fen=principal_fen + bonus_fen,
            bonus_fen=bonus_fen,
            biz_type=BalanceBizType.RECHARGE,
            biz_id=batch_id,
            unique_id=self._unique_id(batch_id, mobile),
            source=BalanceSource.IMPORT,
        )
        await self._repo.mark_row_applied(int(row["id"]))

    async def _rollback_row(self, batch_id: str, row: dict) -> None:
        """回滚单行：扣回本金/赠送金结构并删除导入流水。"""
        mobile = str(row["mobile"])
        principal_fen = int(row["principal_fen"])
        bonus_fen = int(row["bonus_fen"])
        if principal_fen + bonus_fen > 0:
            reverted = await self._balance_repo.deduct_stored_value_with_split(
                mobile, principal_fen + bonus_fen, principal_fen, bonus_fen
            )
            if not reverted:
                raise StoredValueImportError(
                    f"会员 {mask_mobile(mobile)} 余额不足以回滚本批次金额"
                )
        await self._ledger_repo.delete_by_unique_id(self._unique_id(batch_id, mobile))

    async def _find_unsafe_members(
        self, batch_id: str, applied_rows: list[dict]
    ) -> list[tuple[str, str]]:
        """找出导入后已产生后续流水的会员（不满足回滚干净性）。"""
        unsafe: list[tuple[str, str]] = []
        for row in applied_rows:
            mobile = str(row["mobile"])
            ledger = await self._ledger_repo.get_by_unique_id(
                self._unique_id(batch_id, mobile)
            )
            if ledger is None:
                unsafe.append((mobile, "缺少导入流水"))
                continue
            later = await self._ledger_repo.count_after_id(mobile, int(ledger["id"]))
            if later > 0:
                unsafe.append((mobile, f"导入后有 {later} 条后续流水"))
        return unsafe

    async def _validate_row(
        self, row: dict, mobile_counts: Counter
    ) -> tuple[str | None, str]:
        """校验单行，返回 (状态, 错误说明)；状态为 None 表示合格。"""
        mobile = str(row["mobile"])
        if not MOBILE_PATTERN.match(mobile):
            return ROW_STATUS_INVALID, "手机号不是 11 位且 1 开头"
        if mobile_counts[mobile] > 1:
            return ROW_STATUS_INVALID, "文件内手机号重复"
        principal_fen = int(row["principal_fen"])
        bonus_fen = int(row["bonus_fen"])
        if principal_fen < 0 or bonus_fen < 0:
            return ROW_STATUS_INVALID, "本金或赠送金为负数"
        reported = row["reported_total_fen"]
        if reported is not None and principal_fen + bonus_fen != int(reported):
            return ROW_STATUS_INVALID, "本金加赠送金与上报总额不一致"
        existing_fen = await self._balance_repo.get_stored_value_fen(mobile)
        if existing_fen != 0:
            if existing_fen == principal_fen + bonus_fen:
                return ROW_STATUS_CONFLICT, "本地已有等额余额，疑似重复导入"
            return ROW_STATUS_CONFLICT, "本地已存在非零余额，拒绝覆盖"
        return None, ""

    async def _ensure_phone_identity(self, mobile: str, display_name: str) -> str:
        """确保手机号身份链接与客户主档存在，返回客户主档 ID。"""
        link = await self._customer_repo.get_identity_by_value(
            self._tenant_id, CustomerIdentityType.PHONE.value, mobile
        )
        if link is not None:
            return link.customer_id
        masters = await self._customer_repo.get_by_phone(self._tenant_id, mobile)
        if masters:
            customer = masters[0]
        else:
            customer = await self._customer_repo.create_master(
                CustomerMasterCreate(
                    tenant_id=self._tenant_id,
                    primary_phone=mobile,
                    phone_verified=1,
                    display_name=display_name,
                    first_source=CustomerSourceSystem.IMPORT.value,
                    identity_confidence=CustomerIdentityConfidence.HIGH.value,
                )
            )
        await self._customer_repo.create_identity_link(
            CustomerIdentityLinkCreate(
                tenant_id=self._tenant_id,
                customer_id=customer.id,
                identity_type=CustomerIdentityType.PHONE.value,
                identity_value=mobile,
                confidence_score=100,
                verification_status=CustomerIdentityVerificationStatus.VERIFIED.value,
                source_system=CustomerSourceSystem.IMPORT.value,
                source_record_id=mobile,
            )
        )
        return customer.id

    async def _mark_batch_failed(self, batch_id: str, *, note: str) -> None:
        """独立事务写回失败状态（入账/回滚事务已回滚，需补一次提交）。"""
        async with self._repo.transaction():
            await self._repo.mark_batch_failed(batch_id, note=note)

    async def _require_batch(self, batch_id: str) -> dict:
        batch = await self._repo.get_batch(batch_id)
        if batch is None:
            raise StoredValueImportError(f"导入批次不存在: {batch_id}")
        return batch

    def _parse_csv(self, raw_bytes: bytes) -> list[dict]:
        """解析 CSV 为 staging 行字典，校验表头与金额合法性。"""
        text = raw_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        mapping = self._resolve_header(reader.fieldnames)
        rows: list[dict] = []
        for row_no, record in enumerate(reader, start=1):
            rows.append(
                {
                    "row_no": row_no,
                    "mobile": self._cell(record, mapping, "mobile").strip(),
                    "display_name": self._cell(record, mapping, "display_name").strip(),
                    "principal_fen": self._amount(
                        record, mapping, "principal_fen", row_no
                    ),
                    "bonus_fen": self._amount(record, mapping, "bonus_fen", row_no),
                    "reported_total_fen": self._amount(
                        record, mapping, "reported_total_fen", row_no, optional=True
                    ),
                    "yz_open_id": self._cell(record, mapping, "yz_open_id").strip(),
                    "card_no": self._cell(record, mapping, "card_no").strip(),
                    "card_alias": self._cell(record, mapping, "card_alias").strip(),
                }
            )
        return rows

    @staticmethod
    def _resolve_header(fieldnames: list[str] | None) -> dict[str, tuple[str, bool]]:
        """把原始表头解析为 规范字段 -> (原始列名, 是否按元换算)。"""
        mapping: dict[str, tuple[str, bool]] = {}
        for raw_name in fieldnames or []:
            spec = HEADER_SPECS.get((raw_name or "").strip())
            if spec is not None and spec[0] not in mapping:
                mapping[spec[0]] = (raw_name, spec[1])
        missing = [field for field in REQUIRED_FIELDS if field not in mapping]
        if missing:
            raise StoredValueImportError(f"CSV 缺少必需表头: {', '.join(missing)}")
        return mapping

    @staticmethod
    def _cell(record: dict, mapping: dict[str, tuple[str, bool]], field: str) -> str:
        """读取规范字段原始文本，列不存在返回空串。"""
        entry = mapping.get(field)
        if entry is None:
            return ""
        return str(record.get(entry[0]) or "")

    @staticmethod
    def _amount(
        record: dict,
        mapping: dict[str, tuple[str, bool]],
        field: str,
        row_no: int,
        *,
        optional: bool = False,
    ) -> int | None:
        """把金额列解析为整数「分」，只用 Decimal，禁止 float。"""
        entry = mapping.get(field)
        if entry is None:
            return None if optional else 0
        raw = StoredValueImportService._cell(record, mapping, field).strip()
        if raw == "":
            return None if optional else 0
        cleaned = raw.replace(",", "").replace("¥", "").replace("￥", "")
        try:
            value = Decimal(cleaned) * (100 if entry[1] else 1)
        except (InvalidOperation, ValueError) as exc:
            raise StoredValueImportError(
                f"第 {row_no} 行 {field} 不是合法金额: {raw}"
            ) from exc
        integral = value.to_integral_value()
        if integral != value:
            raise StoredValueImportError(
                f"第 {row_no} 行 {field} 不是整数「分」: {raw}"
            )
        return int(integral)

    @staticmethod
    def _row_details(rows: list[dict], status: str) -> list[dict]:
        """提取指定状态行的脱敏明细（不输出完整手机号）。"""
        return [
            {
                "row_no": int(row["row_no"]),
                "mobile": mask_mobile(str(row["mobile"])),
                "error": str(row["error"]),
            }
            for row in rows
            if row["status"] == status
        ]

    @staticmethod
    def _unique_id(batch_id: str, mobile: str) -> str:
        """批次内按会员幂等的储值流水键。"""
        return f"import:{batch_id}:{mobile}"

    @staticmethod
    def _build_batch_id(digest: str) -> str:
        # 拼接随机串：同一文件在同一秒内重试（如回滚后立即重导入）也必须拿到
        # 新的 batch_id，不能因主键冲突而复用或失败。
        stamp = datetime.now().strftime(BATCH_ID_TIME_FORMAT)
        return f"{BATCH_ID_PREFIX}{stamp}_{digest[:8]}_{uuid4().hex[:6]}"


def mask_mobile(mobile: str) -> str:
    """手机号脱敏：保留前 3 位与后 4 位，用于日志与报告。"""
    if len(mobile) <= MOBILE_MASKED_HEAD + MOBILE_MASKED_TAIL:
        return mobile
    return f"{mobile[:MOBILE_MASKED_HEAD]}****{mobile[-MOBILE_MASKED_TAIL:]}"
