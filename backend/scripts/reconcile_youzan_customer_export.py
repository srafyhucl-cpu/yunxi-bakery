"""有赞客户导出（储值 + 积分）迁移与逐会员对账工具。

把有赞门店导出的客户清单（UTF-8 BOM CSV）落到**本地 staging 库**并逐会员
对账：储值余额走既有 StoredValueImportService 期初导入管线（source=import、
批次可回滚），积分走 MemberBalanceRepo.mirror_youzan_points 外部权威镜像。

安全边界（硬约束）：
* 只读源文件，绝不写回有赞导出文件；
* 只写 --staging-db 指定的 staging 库，拒绝落到 backend/data 生产目录，
  也拒绝与生产库配置路径相同的目标；
* 订单本轮不导入（只对储值/积分）；
* 报告中的手机号一律脱敏（前 3 后 4），不输出完整手机号。

用法（先干跑源侧统计，再导入 staging，最后逐会员对账）：
    python scripts/reconcile_youzan_customer_export.py --source <客户数据.csv>
    python scripts/reconcile_youzan_customer_export.py --source <客户数据.csv> --apply
    python scripts/reconcile_youzan_customer_export.py --source <客户数据.csv> --verify
    python scripts/reconcile_youzan_customer_export.py --source <客户数据.csv> \
        --verify --json --output <临时目录>/youzan-reconcile-{timestamp}.json
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import random
import re
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import aiosqlite

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # noqa: E402
from app.database import close_db, init_db, resolve_database_path  # noqa: E402
from app.logger import setup_logger  # noqa: E402
from app.models.customer_master import (  # noqa: E402
    CustomerIdentityConfidence,
    CustomerIdentityLinkCreate,
    CustomerIdentityType,
    CustomerIdentityVerificationStatus,
    CustomerMasterCreate,
    CustomerSourceSystem,
)
from app.repository.customer_master_repo import CustomerMasterRepo  # noqa: E402
from app.repository.member_balance_repo import MemberBalanceRepo  # noqa: E402
from app.service.stored_value.importing import (  # noqa: E402
    BATCH_STATUS_APPLIED,
    StoredValueImportError,
    StoredValueImportService,
    mask_mobile,
)
from app.service.stored_value.member import DEFAULT_TENANT_ID  # noqa: E402

logger = setup_logger()

# 手机号口径与既有认领/导入链路一致：11 位且 1 开头
MOBILE_PATTERN = re.compile(r"^1\d{10}$")
# 积分必须是纯非负整数
POINTS_PATTERN = re.compile(r"^\d+$")

# 源文件列名（与有赞门店导出一致）
COL_MOBILE = "客户手机号"
COL_NAME = "客户姓名"
COL_NICKNAME = "客户昵称"
COL_BALANCE = "客户储值余额"
COL_POINTS = "客户积分"
COL_CARD_ALIAS = "权益卡"

# 归一化 CSV 表头：复用既有储值导入管线的规范列
NORMALIZED_HEADER = (
    "mobile,display_name,principal_fen,bonus_fen,reported_total_fen,"
    "yz_open_id,card_no,card_alias"
)

OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2

# 异常明细按原因抽样，避免 1 万级空号把报告撑爆；计数始终是全量口径
MAX_ANOMALY_SAMPLES_PER_REASON = 20
# 对账随机抽样账户数
VERIFY_SAMPLE_SIZE = 30
# 对账失败明细最多列出多少个脱敏手机号
MAX_VERIFY_FAILURE_DETAILS = 50

# 异常原因枚举
ANOMALY_EMPTY_MOBILE = "empty_mobile"
ANOMALY_INVALID_MOBILE = "invalid_mobile"
ANOMALY_DUPLICATE_MOBILE = "duplicate_mobile"
ANOMALY_BALANCE_INVALID = "balance_invalid"
ANOMALY_BALANCE_PRECISION = "balance_precision"
ANOMALY_NEGATIVE_BALANCE = "negative_balance"
ANOMALY_POINTS_INVALID = "points_invalid"
ANOMALY_NEGATIVE_POINTS = "negative_points"


def default_staging_db_path() -> Path:
    """默认 staging 库位置：系统临时目录 stage5/youzan_staging.db。"""
    return Path(tempfile.gettempdir()) / "stage5" / "youzan_staging.db"


@dataclass(frozen=True)
class CustomerRecord:
    """客户导出文件里的一条已解析记录（仅含有效手机号）。"""

    row_no: int
    mobile: str
    display_name: str
    stored_value_fen: int
    points: int
    card_alias: str


@dataclass
class SourceSnapshot:
    """源文件解析快照：记录清单、异常明细与源侧统计。"""

    source_path: str
    source_sha256: str
    total_rows: int
    records: list[CustomerRecord] = field(default_factory=list)
    anomalies: list[dict] = field(default_factory=list)
    anomaly_counts: dict[str, int] = field(default_factory=dict)
    anomaly_total: int = 0
    empty_mobile_rows: int = 0
    invalid_mobile_rows: int = 0
    duplicate_mobile_rows: int = 0
    points_accounts_all_rows: int = 0
    points_total_all_rows: int = 0


def mask_any(value: str) -> str:
    """脱敏任意手机号形态：有效手机号按前 3 后 4 脱敏，短值只留长度。"""
    cleaned = value.strip()
    if not cleaned:
        return "<empty>"
    if len(cleaned) <= 7:
        return f"<invalid:{len(cleaned)}chars>"
    return mask_mobile(cleaned)


def parse_amount_yuan_to_fen(raw: str) -> tuple[int | None, str]:
    """把「元」金额解析为整数「分」；返回 (分值, 异常原因)。"""
    cleaned = raw.replace(",", "").replace("¥", "").replace("￥", "").strip()
    if not cleaned:
        return 0, ""
    try:
        value = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None, ANOMALY_BALANCE_INVALID
    if value < 0:
        return None, ANOMALY_NEGATIVE_BALANCE
    fen = value * 100
    if fen != fen.to_integral_value():
        return None, ANOMALY_BALANCE_PRECISION
    return int(fen), ""


def parse_points(raw: str) -> tuple[int | None, str]:
    """把积分列解析为非负整数；返回 (积分, 异常原因)。"""
    cleaned = raw.strip()
    if not cleaned:
        return 0, ""
    if not POINTS_PATTERN.match(cleaned):
        if cleaned.startswith("-"):
            return None, ANOMALY_NEGATIVE_POINTS
        return None, ANOMALY_POINTS_INVALID
    return int(cleaned), ""


def _cell(record: dict, column: str) -> str:
    """读取 CSV 列文本，列不存在或为空返回空串。"""
    return str(record.get(column) or "").strip()


def _append_anomaly(
    anomalies: list[dict],
    counts: Counter,
    row_no: int,
    reason: str,
    mobile: str,
    detail: str,
) -> None:
    """登记一条异常明细（手机号脱敏）。"""
    counts[reason] += 1
    anomalies.append(
        {
            "row_no": row_no,
            "reason": reason,
            "mobile": mask_any(mobile),
            "detail": detail,
        }
    )


def parse_source_csv(source_path: Path) -> SourceSnapshot:
    """解析有赞客户导出 CSV，返回记录清单、异常明细与源侧统计。

    口径：手机号只接受 11 位 1 开头；余额按「元」用 Decimal 换算「分」，
    超过 2 位小数一律拒绝；积分只接受非负整数。空号/非法号/重复号不导入。
    """
    raw_bytes = source_path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    total_rows = 0
    anomalies: list[dict] = []
    counts: Counter = Counter()
    mobile_counter: Counter = Counter()
    parsed_rows: list[tuple[int, str, str, int, int, str]] = []
    empty_mobile_rows = 0
    invalid_mobile_rows = 0
    points_accounts_all_rows = 0
    points_total_all_rows = 0

    for row_no, record in enumerate(reader, start=1):
        total_rows += 1
        mobile = _cell(record, COL_MOBILE)
        display_name = _cell(record, COL_NAME) or _cell(record, COL_NICKNAME)
        card_alias = _cell(record, COL_CARD_ALIAS)

        if not mobile:
            empty_mobile_rows += 1
            _append_anomaly(
                anomalies, counts, row_no, ANOMALY_EMPTY_MOBILE, mobile, "手机号为空"
            )
        elif not MOBILE_PATTERN.match(mobile):
            invalid_mobile_rows += 1
            _append_anomaly(
                anomalies,
                counts,
                row_no,
                ANOMALY_INVALID_MOBILE,
                mobile,
                "手机号不是 11 位且 1 开头",
            )
        else:
            mobile_counter[mobile] += 1

        balance_fen, balance_reason = parse_amount_yuan_to_fen(
            _cell(record, COL_BALANCE)
        )
        if balance_reason:
            _append_anomaly(
                anomalies,
                counts,
                row_no,
                balance_reason,
                mobile,
                f"储值余额不是合法金额: {_cell(record, COL_BALANCE)}",
            )

        points, points_reason = parse_points(_cell(record, COL_POINTS))
        if points_reason:
            _append_anomaly(
                anomalies,
                counts,
                row_no,
                points_reason,
                mobile,
                f"积分不是非负整数: {_cell(record, COL_POINTS)}",
            )
        elif points is not None and points > 0:
            points_accounts_all_rows += 1
            points_total_all_rows += points

        if balance_fen is None:
            balance_fen = 0
        if points is None:
            points = 0
        parsed_rows.append(
            (row_no, mobile, display_name, balance_fen, points, card_alias)
        )

    records: list[CustomerRecord] = []
    duplicate_mobile_rows = 0
    for row_no, mobile, display_name, balance_fen, points, card_alias in parsed_rows:
        if not mobile:
            continue
        if not MOBILE_PATTERN.match(mobile):
            continue
        if mobile_counter[mobile] > 1:
            duplicate_mobile_rows += 1
            _append_anomaly(
                anomalies,
                counts,
                row_no,
                ANOMALY_DUPLICATE_MOBILE,
                mobile,
                "文件内手机号重复",
            )
            continue
        records.append(
            CustomerRecord(
                row_no=row_no,
                mobile=mobile,
                display_name=display_name,
                stored_value_fen=balance_fen,
                points=points,
                card_alias=card_alias,
            )
        )

    return SourceSnapshot(
        source_path=str(source_path),
        source_sha256=digest,
        total_rows=total_rows,
        records=records,
        anomalies=anomalies,
        anomaly_counts=dict(counts),
        anomaly_total=len(anomalies),
        empty_mobile_rows=empty_mobile_rows,
        invalid_mobile_rows=invalid_mobile_rows,
        duplicate_mobile_rows=duplicate_mobile_rows,
        points_accounts_all_rows=points_accounts_all_rows,
        points_total_all_rows=points_total_all_rows,
    )


def build_source_stats(snapshot: SourceSnapshot) -> dict:
    """汇总源侧统计：行数、手机号分布、储值与积分口径。"""
    nonzero_records = [r for r in snapshot.records if r.stored_value_fen > 0]
    nonzero_total_fen = sum(r.stored_value_fen for r in nonzero_records)
    points_records = [r for r in snapshot.records if r.points > 0]
    points_total = sum(r.points for r in points_records)
    samples = _sample_anomalies(snapshot.anomalies)
    return {
        "source_sha256": snapshot.source_sha256,
        "total_rows": snapshot.total_rows,
        "valid_mobile_rows": len(snapshot.records),
        "empty_mobile_rows": snapshot.empty_mobile_rows,
        "invalid_mobile_rows": snapshot.invalid_mobile_rows,
        "duplicate_mobile_rows": snapshot.duplicate_mobile_rows,
        "nonzero_balance_accounts": len(nonzero_records),
        "nonzero_balance_total_fen": nonzero_total_fen,
        "nonzero_balance_total_yuan": f"{nonzero_total_fen / 100:.2f}",
        "zero_balance_accounts": len(snapshot.records) - len(nonzero_records),
        "points_accounts": len(points_records),
        "points_total": points_total,
        "points_accounts_all_rows": snapshot.points_accounts_all_rows,
        "points_total_all_rows": snapshot.points_total_all_rows,
        "anomaly_total": snapshot.anomaly_total,
        "anomaly_counts": snapshot.anomaly_counts,
        "anomalies": samples["items"],
        "anomalies_truncated": samples["truncated"],
    }


def _sample_anomalies(anomalies: list[dict]) -> dict:
    """按异常原因抽样明细，计数仍是全量口径。"""
    per_reason: Counter = Counter()
    items: list[dict] = []
    for anomaly in anomalies:
        reason = str(anomaly["reason"])
        if per_reason[reason] >= MAX_ANOMALY_SAMPLES_PER_REASON:
            continue
        per_reason[reason] += 1
        items.append(anomaly)
    return {"items": items, "truncated": len(items) < len(anomalies)}


def write_normalized_csv(snapshot: SourceSnapshot, target_dir: Path) -> Path:
    """生成储值导入用的归一化 CSV（只含非零余额账户，全部按本金入账）。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = target_dir / "youzan_customer_export_normalized.csv"
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(NORMALIZED_HEADER.split(","))
    for record in snapshot.records:
        if record.stored_value_fen <= 0:
            continue
        writer.writerow(
            [
                record.mobile,
                record.display_name,
                record.stored_value_fen,
                0,
                record.stored_value_fen,
                "",
                "",
                record.card_alias,
            ]
        )
    normalized_path.write_text(buffer.getvalue(), encoding="utf-8", newline="")
    return normalized_path


async def ensure_customer_master(
    customer_repo: CustomerMasterRepo,
    *,
    tenant_id: str,
    record: CustomerRecord,
) -> str:
    """确保手机号身份与客户主档存在，返回客户主档 ID。

    口径与储值导入管线一致：优先复用手机号身份链接，其次复用同号主档，
    都没有时按「导入」来源新建主档并建立手机号身份链接。
    """
    link = await customer_repo.get_identity_by_value(
        tenant_id, CustomerIdentityType.PHONE.value, record.mobile
    )
    if link is not None:
        return link.customer_id
    masters = await customer_repo.get_by_phone(tenant_id, record.mobile)
    if masters:
        customer = masters[0]
    else:
        customer = await customer_repo.create_master(
            CustomerMasterCreate(
                tenant_id=tenant_id,
                primary_phone=record.mobile,
                phone_verified=1,
                display_name=record.display_name,
                first_source=CustomerSourceSystem.IMPORT.value,
                identity_confidence=CustomerIdentityConfidence.HIGH.value,
            )
        )
    await customer_repo.create_identity_link(
        CustomerIdentityLinkCreate(
            tenant_id=tenant_id,
            customer_id=customer.id,
            identity_type=CustomerIdentityType.PHONE.value,
            identity_value=record.mobile,
            confidence_score=100,
            verification_status=CustomerIdentityVerificationStatus.VERIFIED.value,
            source_system=CustomerSourceSystem.IMPORT.value,
            source_record_id=record.mobile,
        )
    )
    return customer.id


async def import_points(
    conn: aiosqlite.Connection,
    snapshot: SourceSnapshot,
    *,
    tenant_id: str,
) -> dict:
    """把有赞侧权威积分镜像进 staging 库（每客户幂等）。

    积分走 MemberBalanceRepo.mirror_youzan_points（锚点 + 偏移），本地账本
    净额不受影响；先 upsert_identity 建档时**不传** stored_value_fen，
    绝不覆盖已导入的储值余额。单客户失败只记录明细，不中断整批。
    """
    balance_repo = MemberBalanceRepo(conn)
    customer_repo = CustomerMasterRepo(conn)
    failures: list[dict] = []
    mirrored_count = 0
    for record in snapshot.records:
        if record.points <= 0:
            continue
        try:
            customer_id = await ensure_customer_master(
                customer_repo, tenant_id=tenant_id, record=record
            )
            await balance_repo.upsert_identity(
                mobile=record.mobile,
                customer_id=customer_id,
                display_name=record.display_name,
                is_member=1,
            )
            await balance_repo.mirror_youzan_points(
                mobile=record.mobile,
                customer_id=customer_id,
                youzan_total=record.points,
            )
            mirrored_count += 1
        except Exception as exc:
            # 单客户失败必须留痕：记录脱敏明细后继续下一位，绝不整批静默跳过
            logger.error(
                "积分镜像失败 mobile=%s err=%s", mask_mobile(record.mobile), exc
            )
            failures.append(
                {"mobile": mask_any(record.mobile), "error": str(exc)[:200]}
            )
    await conn.commit()
    return {
        "points_accounts": sum(1 for r in snapshot.records if r.points > 0),
        "points_total": sum(r.points for r in snapshot.records),
        "points_mirrored": mirrored_count,
        "failed_count": len(failures),
        "failed_details": failures,
    }


def assert_staging_path_allowed(staging_db_path: Path) -> Path:
    """拒绝把 staging 库落在生产目录或生产库路径上。"""
    resolved = staging_db_path.resolve()
    production_dir = (ROOT_DIR / "data").resolve()
    if resolved == production_dir or production_dir in resolved.parents:
        raise ValueError(f"staging 库不得写入生产目录: {resolved}")
    production_db = Path(resolve_database_path(settings.DB_PATH)).resolve()
    if resolved == production_db:
        raise ValueError(f"staging 库不得与生产库同一路径: {resolved}")
    return resolved


async def run_apply(
    *,
    source_path: Path,
    staging_db_path: Path,
    tenant_id: str,
) -> tuple[dict, dict]:
    """在 staging 库上完成储值 + 积分导入，返回 (源侧统计, 导入报告)。"""
    snapshot = parse_source_csv(source_path)
    source_stats = build_source_stats(snapshot)
    staging_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = await init_db(str(staging_db_path))
    try:
        normalized_path = write_normalized_csv(snapshot, staging_db_path.parent)
        service = StoredValueImportService(conn, tenant_id=tenant_id)
        batch = await service.create_batch_from_csv(normalized_path)
        validated = await service.validate_batch(str(batch["id"]))
        if int(validated["invalid_rows"]) > 0:
            return source_stats, {
                "batch_id": str(batch["id"]),
                "batch_status": str(validated["status"]),
                "balance_rows": int(validated["valid_rows"]),
                "balance_total_fen": int(validated["expected_total_fen"]),
                "balance_applied_fen": int(validated["applied_total_fen"]),
                "balance_variance_fen": 0,
                "invalid_rows": int(validated["invalid_rows"]),
                "invalid_details": validated["invalid_details"],
                "normalized_csv": str(normalized_path),
                "applied": False,
                "points_accounts": 0,
                "points_total": 0,
                "points_mirrored": 0,
                "failed_count": 0,
                "failed_details": [],
            }
        applied = await service.apply_batch(str(batch["id"]))
        if str(applied["status"]) != BATCH_STATUS_APPLIED:
            raise StoredValueImportError(
                f"储值批次未成功入账: status={applied['status']}"
            )
        points_result = await import_points(conn, snapshot, tenant_id=tenant_id)
        return source_stats, {
            "batch_id": str(applied["batch_id"]),
            "batch_status": str(applied["status"]),
            "balance_rows": int(applied["applied_rows"]),
            "balance_total_fen": int(applied["expected_total_fen"]),
            "balance_applied_fen": int(applied["applied_total_fen"]),
            "balance_variance_fen": int(applied["variance_fen"]),
            "principal_variance_fen": int(applied["principal_variance_fen"]),
            "bonus_variance_fen": int(applied["bonus_variance_fen"]),
            "invalid_rows": int(applied["invalid_rows"]),
            "invalid_details": applied["invalid_details"],
            "normalized_csv": str(normalized_path),
            "applied": True,
            **points_result,
        }
    finally:
        await close_db(conn)


async def _read_target_balances(staging_db_path: Path) -> dict[str, dict]:
    """读取 staging 库 member_balance 快照（只读连接，不改库）。"""
    uri = staging_db_path.resolve().as_uri() + "?mode=ro"
    conn = await aiosqlite.connect(uri, uri=True)
    try:
        conn.row_factory = aiosqlite.Row
        rows = await conn.execute_fetchall(
            "SELECT mobile, stored_value_fen, principal_fen, bonus_fen, points "
            "FROM member_balance"
        )
    finally:
        await conn.close()
    return {str(row["mobile"]): dict(row) for row in rows}


async def run_verify(
    *,
    source_path: Path,
    staging_db_path: Path,
) -> tuple[dict, dict]:
    """逐会员比对源文件与 staging 库，返回 (源侧统计, 对账报告)。"""
    snapshot = parse_source_csv(source_path)
    source_stats = build_source_stats(snapshot)
    if not staging_db_path.exists():
        raise FileNotFoundError(f"staging 库不存在，先执行 --apply: {staging_db_path}")
    target_rows = await _read_target_balances(staging_db_path)

    variance_details: list[dict] = []
    balance_variance_fen = 0
    points_variance = 0
    target_nonzero_accounts = 0
    target_balance_total_fen = 0
    target_points_total = 0
    source_nonzero_records: list[CustomerRecord] = []

    for record in snapshot.records:
        target = target_rows.get(record.mobile)
        target_sv = int(target["stored_value_fen"]) if target else 0
        target_principal = int(target["principal_fen"]) if target else 0
        target_bonus = int(target["bonus_fen"]) if target else 0
        target_points = int(target["points"]) if target else 0

        if target_sv > 0:
            target_nonzero_accounts += 1
            target_balance_total_fen += target_sv
        target_points_total += target_points
        if record.stored_value_fen > 0:
            source_nonzero_records.append(record)

        balance_variance_fen += record.stored_value_fen - target_sv
        points_variance += record.points - target_points

        mismatches = []
        if target_sv != record.stored_value_fen:
            mismatches.append("stored_value_fen")
        if target_principal != record.stored_value_fen:
            mismatches.append("principal_fen")
        if target_bonus != 0:
            mismatches.append("bonus_fen")
        if target_points != record.points:
            mismatches.append("points")
        if mismatches:
            variance_details.append(
                {
                    "mobile": mask_any(record.mobile),
                    "fields": mismatches,
                    "source_stored_value_fen": record.stored_value_fen,
                    "target_stored_value_fen": target_sv,
                    "source_principal_fen": record.stored_value_fen,
                    "target_principal_fen": target_principal,
                    "source_bonus_fen": 0,
                    "target_bonus_fen": target_bonus,
                    "source_points": record.points,
                    "target_points": target_points,
                }
            )

    known_mobiles = {record.mobile for record in snapshot.records}
    extra_mobiles = [
        mask_any(mobile)
        for mobile in target_rows
        if mobile and mobile not in known_mobiles
    ]

    source_nonzero_total_fen = sum(r.stored_value_fen for r in source_nonzero_records)
    source_points_accounts = sum(1 for r in snapshot.records if r.points > 0)
    source_points_total = sum(r.points for r in snapshot.records)

    return source_stats, {
        "source_nonzero_accounts": len(source_nonzero_records),
        "target_nonzero_accounts": target_nonzero_accounts,
        "source_balance_total_fen": source_nonzero_total_fen,
        "source_balance_total_yuan": f"{source_nonzero_total_fen / 100:.2f}",
        "target_balance_total_fen": target_balance_total_fen,
        "target_balance_total_yuan": f"{target_balance_total_fen / 100:.2f}",
        "balance_variance_fen": balance_variance_fen,
        "variance_count": len(variance_details),
        "points_source_accounts": source_points_accounts,
        "points_target_accounts": sum(
            1 for row in target_rows.values() if int(row["points"]) > 0
        ),
        "points_source_total": source_points_total,
        "points_target_total": target_points_total,
        "points_variance": points_variance,
        "extra_accounts_count": len(extra_mobiles),
        "extra_accounts": extra_mobiles[:MAX_VERIFY_FAILURE_DETAILS],
        "failed_mobiles": [detail["mobile"] for detail in variance_details][
            :MAX_VERIFY_FAILURE_DETAILS
        ],
        "variance_details": variance_details[:MAX_VERIFY_FAILURE_DETAILS],
        "samples": _build_verify_samples(source_nonzero_records, target_rows),
    }


def _build_verify_samples(
    source_nonzero_records: list[CustomerRecord],
    target_rows: dict[str, dict],
) -> list[dict]:
    """随机抽取非零余额账户明细（固定随机种子，保证报告可复现）。"""
    if not source_nonzero_records:
        return []
    rng = random.Random(20260814)
    picked = rng.sample(
        source_nonzero_records, min(VERIFY_SAMPLE_SIZE, len(source_nonzero_records))
    )
    samples = []
    for record in picked:
        target = target_rows.get(record.mobile)
        samples.append(
            {
                "mobile": mask_any(record.mobile),
                "source_stored_value_fen": record.stored_value_fen,
                "target_stored_value_fen": int(target["stored_value_fen"])
                if target
                else 0,
                "source_principal_fen": record.stored_value_fen,
                "target_principal_fen": int(target["principal_fen"]) if target else 0,
                "source_bonus_fen": 0,
                "target_bonus_fen": int(target["bonus_fen"]) if target else 0,
                "source_points": record.points,
                "target_points": int(target["points"]) if target else 0,
                "matched": bool(
                    target
                    and int(target["stored_value_fen"]) == record.stored_value_fen
                    and int(target["principal_fen"]) == record.stored_value_fen
                    and int(target["bonus_fen"]) == 0
                    and int(target["points"]) == record.points
                ),
            }
        )
    return samples


def expand_output_path(output_path_value: str) -> Path:
    """展开报告输出路径中的 {timestamp} 占位符。"""
    timestamp = datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)
    return Path(output_path_value.replace(OUTPUT_TIMESTAMP_PLACEHOLDER, timestamp))


def ensure_output_path_available(output_path_value: str) -> Path:
    """报告文件已存在时拒绝覆盖。"""
    output_path = expand_output_path(output_path_value)
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")
    return output_path


def build_payload(
    *,
    mode: str,
    status: str,
    source_path: Path,
    staging_db_path: Path,
    tenant_id: str,
    source_stats: dict,
    import_report: dict | None,
    verify_report: dict | None,
) -> dict:
    """组装稳定字段的 JSON 报告。"""
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "status": status,
        "mode": mode,
        "metadata": {
            "generated_at": generated_at,
            "script": "reconcile_youzan_customer_export",
            "source_file": str(source_path),
            "staging_db": str(staging_db_path),
            "tenant_id": tenant_id,
            "project_root": str(ROOT_DIR),
        },
        "source": source_stats,
        "import": import_report,
        "verify": verify_report,
    }


def print_summary(payload: dict) -> None:
    """输出人类可读的对账摘要。"""
    source = payload["source"]
    print("Youzan customer export reconcile")
    print(f"mode={payload['mode']} status={payload['status']}")
    print(f"total_rows={source['total_rows']}")
    print(
        "mobile_valid={valid} empty={empty} invalid={invalid} duplicate={dup}".format(
            valid=source["valid_mobile_rows"],
            empty=source["empty_mobile_rows"],
            invalid=source["invalid_mobile_rows"],
            dup=source["duplicate_mobile_rows"],
        )
    )
    print(
        "nonzero_balance_accounts={count} total_fen={fen} total_yuan={yuan}".format(
            count=source["nonzero_balance_accounts"],
            fen=source["nonzero_balance_total_fen"],
            yuan=source["nonzero_balance_total_yuan"],
        )
    )
    print(
        "points_accounts={count} points_total={total}".format(
            count=source["points_accounts"], total=source["points_total"]
        )
    )
    print(
        f"anomaly_total={source['anomaly_total']} anomaly_counts={source['anomaly_counts']}"
    )
    import_report = payload["import"]
    if import_report:
        print(
            "batch_id={batch} batch_status={status} balance_rows={rows} "
            "balance_variance_fen={variance}".format(
                batch=import_report["batch_id"],
                status=import_report["batch_status"],
                rows=import_report["balance_rows"],
                variance=import_report["balance_variance_fen"],
            )
        )
        print(
            "points_mirrored={mirrored} points_failed={failed}".format(
                mirrored=import_report.get("points_mirrored", 0),
                failed=import_report.get("failed_count", 0),
            )
        )
    verify_report = payload["verify"]
    if verify_report:
        print(
            "verify_nonzero_source={source} target={target} balance_variance_fen={fen} "
            "variance_count={count}".format(
                source=verify_report["source_nonzero_accounts"],
                target=verify_report["target_nonzero_accounts"],
                fen=verify_report["balance_variance_fen"],
                count=verify_report["variance_count"],
            )
        )
        print(
            "verify_points_source_total={source} target_total={target} "
            "points_variance={variance}".format(
                source=verify_report["points_source_total"],
                target=verify_report["points_target_total"],
                variance=verify_report["points_variance"],
            )
        )


def emit(payload: dict, *, as_json: bool, output: Path | None) -> None:
    """输出报告：JSON 走 stdout 或文件，文本模式打印摘要。"""
    if as_json:
        json_bytes = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        if output is None:
            sys.stdout.buffer.write(json_bytes)
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(json_bytes)
        return
    print_summary(payload)


async def async_main(argv: list[str] | None = None) -> int:
    """CLI 入口：dry-run / apply / verify。"""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.output and not args.json:
        print("--output 必须配合 --json 使用。", file=sys.stderr)
        return EXIT_USAGE

    output_path: Path | None = None
    if args.output:
        try:
            output_path = ensure_output_path_available(args.output)
        except FileExistsError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_USAGE

    source_path = Path(args.source).expanduser()
    if not source_path.exists():
        print(f"源文件不存在: {source_path}", file=sys.stderr)
        return EXIT_USAGE

    try:
        staging_db_path = assert_staging_path_allowed(Path(args.staging_db))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE

    mode = "dry-run"
    if args.apply:
        mode = "apply"
    elif args.verify:
        mode = "verify"

    try:
        if mode == "apply":
            source_stats, import_report = await run_apply(
                source_path=source_path,
                staging_db_path=staging_db_path,
                tenant_id=args.tenant_id,
            )
            failed_count = int(import_report.get("failed_count", 0))
            applied = bool(import_report.get("applied"))
            status = "ok" if applied and failed_count == 0 else "failed"
            exit_code = EXIT_OK if status == "ok" else EXIT_REFUSED
            payload = build_payload(
                mode=mode,
                status=status,
                source_path=source_path,
                staging_db_path=staging_db_path,
                tenant_id=args.tenant_id,
                source_stats=source_stats,
                import_report=import_report,
                verify_report=None,
            )
        elif mode == "verify":
            source_stats, verify_report = await run_verify(
                source_path=source_path, staging_db_path=staging_db_path
            )
            consistent = (
                verify_report["variance_count"] == 0
                and verify_report["balance_variance_fen"] == 0
                and verify_report["points_variance"] == 0
            )
            status = "ok" if consistent else "failed"
            exit_code = EXIT_OK if consistent else EXIT_REFUSED
            payload = build_payload(
                mode=mode,
                status=status,
                source_path=source_path,
                staging_db_path=staging_db_path,
                tenant_id=args.tenant_id,
                source_stats=source_stats,
                import_report=None,
                verify_report=verify_report,
            )
        else:
            snapshot = parse_source_csv(source_path)
            source_stats = build_source_stats(snapshot)
            payload = build_payload(
                mode=mode,
                status="ok",
                source_path=source_path,
                staging_db_path=staging_db_path,
                tenant_id=args.tenant_id,
                source_stats=source_stats,
                import_report=None,
                verify_report=None,
            )
            exit_code = EXIT_OK
    except StoredValueImportError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_REFUSED
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE

    emit(payload, as_json=args.json, output=output_path)
    return exit_code


def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description=("有赞客户导出迁移与逐会员储值/积分对账（默认只写本地 staging 库）")
    )
    parser.add_argument(
        "--source", required=True, help="有赞客户导出 CSV 路径（只读，绝不写回）。"
    )
    parser.add_argument(
        "--staging-db",
        default=str(default_staging_db_path()),
        help=(
            "staging SQLite 路径，默认写系统临时目录 stage5/youzan_staging.db；"
            "拒绝指向 backend/data 生产目录或生产库。"
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="只解析源文件并输出源侧统计，不建库不写库（默认行为）。",
    )
    mode.add_argument(
        "--apply", action="store_true", help="建 staging 库并导入储值余额与积分。"
    )
    mode.add_argument(
        "--verify", action="store_true", help="对已有 staging 库做逐会员储值/积分对账。"
    )
    parser.add_argument(
        "--tenant-id", default=DEFAULT_TENANT_ID, help="客户主档租户 ID，默认 yunxi。"
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON。")
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "配合 --json 使用，将报告写入指定文件；目标已存在时拒绝覆盖；"
            "支持 {timestamp} 自动展开为 YYYYMMDD-HHMMSS。"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
