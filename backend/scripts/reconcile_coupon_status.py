"""券状态冲突对账：把本地券事实与有赞当前券状态逐条对齐。

背景
----
2026-10-20 券/卡 API 契约修复上线后，券镜像已经能取到有赞当前券数据，但生产
`coupon_inventory` 里仍留着一批「骨架券行」（`title=''` 且 `value_fen=0` 且
`template_id=''`）。骨架行里最危险的不是缺字段，而是**状态与事实相反**：

- 本地记 `TAKE`（客户持有）、有赞记 `USED`（客户已在有赞侧用掉）：小程序会把
  这张券当成可用券，客户再来一次就是二次抵扣（资损）；
- 本地记 `TAKE`、有赞记 `INVALID`（已失效且未使用）：本地券账本没有「已过期」
  状态，只能靠有效期把它挡在可用之外。

本脚本做什么
------------
按手机号逐个向有赞核对当前券状态，并按分类落库：

- 本地 `TAKE` + 有赞 `USED`：新增一条本地 `CONSUME` 事实行
  （`order_no=used_in_order_no`、`occurred_at=used_at`、面额/模板/有效期取有赞
  当前值），使「最新状态」落在 `CONSUME`；**不删除旧行、不修改历史 `TAKE` 行的
  状态**；
- 本地 `TAKE` + 有赞 `INVALID`（未使用）：补全 `title`/面额/模板/有效期，且
  有效期必须取券自身的过期时间（已过期），让本地券引擎按过期拒绝；状态仍是
  `TAKE`，但不再可抵扣；
- 本地 `CONSUME` + 有赞 `USED`：只补全元数据，**不重复插入** `CONSUME` 行；
- 本地 `TAKE` + 有赞 `VALID`：补全元数据（与已完成的定向回填口径一致）；
- 有赞查不到 / 状态歧义 / 过期时间无法证明：保留原行，分类报告，绝不猜。

口径要点
--------
- 有赞「已失效且未使用」的券**不**出现在 `list_customer_coupons` 的合并结果里
  （该方法会过滤 `INVALID` 且未使用的券），因此过期券必须**单独**按 `INVALID`
  状态查一次原始返回集，否则会被误判成「查不到」。
- 唯一键 `(coupon_id, status, mobile, cycle_no)`：重复执行不会重复插入；已存在
  `CONSUME` 行时改为补全元数据（幂等）。
- 过期券只有在**能证明过期时间早于今天**时才补面额与模板：只补面额不补过期
  时间会把过期券变成可用券（资损）。
- 单事务写入：任一行异常整体回滚，绝不部分落库。
- 不改 `member_balance` / `points_ledger`，不删除任何 `coupon_inventory` 行，
  不修改任何既有行的 `status`。

安全约束
--------
- 必须显式传 `--db`，脚本不猜测任何默认库路径；
- 默认 dry-run（SQLite `mode=ro` 只读打开，全程只读），只有 `--apply` 才写库；
- 路径疑似生产部署目录时必须额外传 `--allow-production`；
- 报告字段固定、手机号脱敏。

用法
----
    # 默认 dry-run：只出报告，不写库
    python scripts/reconcile_coupon_status.py --db /path/to/bot.db

    # 核对通过后落库（生产路径必须显式声明）
    python scripts/reconcile_coupon_status.py \
        --db /opt/apps/yunxi-bakery/backend/data/bot.db --apply --allow-production
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

BEIJING_TZ = timezone(timedelta(hours=8))


def _detect_backend_dir() -> Path:
    """定位 backend 根目录：优先脚本自身所在仓库，其次当前工作目录。

    脚本随仓库部署时（backend/scripts/）第一命中；被单独拷贝到临时目录执行时
    退化为当前工作目录，使 `app.*` 仍指向被部署的那份后端代码。
    """
    for candidate in (
        Path(__file__).resolve().parent.parent,
        Path.cwd().resolve(),
    ):
        if (candidate / "app" / "__init__.py").is_file():
            return candidate
    return Path(__file__).resolve().parent.parent


BACKEND_DIR = _detect_backend_dir()
for _sys_path in (str(BACKEND_DIR), str(BACKEND_DIR / "scripts")):
    if _sys_path not in sys.path:
        sys.path.insert(0, _sys_path)

from app.config import settings  # noqa: E402
from app.service.coupon.template_sync import (  # noqa: E402
    extract_template_fields,
    parse_youzan_template,
)
from app.service.youzan.member_api import (  # noqa: E402
    COUPON_CODE_LIST_API_NAME,
    COUPON_CODE_LIST_API_VERSION,
    COUPON_LIST_API_NAME,
    COUPON_LIST_API_VERSION,
    COUPON_STATUS_INVALID,
)
from app.service.youzan.member_helpers import to_fen  # noqa: E402
from app.utils import format_millis_datetime, now_str  # noqa: E402
from resolve_youzan_dead_letters import (  # noqa: E402
    looks_like_production_path,
    mask_sensitive,
)

# 骨架券行的判定条件：券名、面额、模板 ID 三者同时为空。
STALE_TITLE = ""
STALE_VALUE_FEN = 0
STALE_TEMPLATE_ID = ""

# 本地券账本状态（只认这三个词表）。
LOCAL_STATUS_TAKE = "TAKE"
LOCAL_STATUS_CONSUME = "CONSUME"

# 新增事实行的来源：有赞侧观察到的核销事实，与全量导入路径同口径。
SOURCE_IMPORT = "import"

# 有赞券现状分类。
YOZAN_USED = "USED"
YOZAN_VALID = "VALID"
YOZAN_INVALID = "INVALID"
YOZAN_UNKNOWN = "UNKNOWN"
YOZAN_NOT_FOUND = "NOT_FOUND"

# 对账结论分类。
CATEGORY_CONSUME_INSERTED = "consume_fact_inserted"
CATEGORY_CONSUME_ALIGNED = "consume_fact_aligned"
CATEGORY_CONSUME_METADATA = "consume_metadata_filled"
CATEGORY_EXPIRED_FILLED = "expired_filled"
CATEGORY_VALID_ALIGNED = "valid_aligned"
CATEGORY_KEPT = "kept"

# 写动作。
ACTION_KEEP = "keep"
ACTION_INSERT_CONSUME = "insert_consume"
ACTION_UPDATE_CONSUME = "update_consume"
ACTION_UPDATE_ROW = "update_row"

# 稳定原因码。
REASON_USED_CONFLICT = "youzan_used_local_take_conflict"
REASON_USED_EXISTING = "youzan_used_consume_row_exists"
REASON_USED_CONSUME_METADATA = "youzan_used_local_consume_metadata"
REASON_INVALID_EXPIRED = "youzan_invalid_unused_expired"
REASON_VALID_ALIGNED = "youzan_valid_aligned"
REASON_NOT_FOUND = "coupon_not_found_in_youzan"
REASON_STATUS_CONFLICT = "status_conflict_with_youzan"
REASON_QUERY_FAILED = "youzan_query_failed"
REASON_MOBILE_MISSING = "mobile_missing"
REASON_COUPON_ID_MISSING = "coupon_id_missing"
REASON_LOCAL_STATUS_UNSUPPORTED = "local_status_unsupported"
REASON_EXPIRY_UNPROVABLE = "expiry_not_provable"
REASON_TEMPLATE_MISSING = "coupon_template_missing"
REASON_TITLE_MISSING = "coupon_title_missing"

REASON_TEXT = {
    REASON_USED_CONFLICT: "有赞已核销、本地记持有：新增本地 CONSUME 事实行",
    REASON_USED_EXISTING: "已存在本地 CONSUME 行：只补全元数据，不重复插入",
    REASON_USED_CONSUME_METADATA: "本地已是 CONSUME：只补全元数据",
    REASON_INVALID_EXPIRED: "有赞已失效未使用：补全元数据并按过期拒绝",
    REASON_VALID_ALIGNED: "有赞当前有效：与本地持有事实一致，补全元数据",
    REASON_NOT_FOUND: "有赞侧查不到该券：保留原行，不猜",
    REASON_STATUS_CONFLICT: "有赞与本地状态互相矛盾：保留原行，人工判定",
    REASON_QUERY_FAILED: "有赞接口调用失败：本行结论未知，保留原行",
    REASON_MOBILE_MISSING: "行上没有手机号，无法向有赞核对",
    REASON_COUPON_ID_MISSING: "行上没有 coupon_id，无法向有赞核对",
    REASON_LOCAL_STATUS_UNSUPPORTED: "本地状态不在 TAKE/CONSUME 词表内，保留原行",
    REASON_EXPIRY_UNPROVABLE: "无法证明券已过期：只补面额会让过期券变可用，保留原行",
    REASON_TEMPLATE_MISSING: "有赞券模板详情缺失，面额与有效期无从取得",
    REASON_TITLE_MISSING: "有赞券与模板都没有给出券名",
}

TARGET_ROWS_SQL = (
    "SELECT id, coupon_id, coupon_group_id, customer_id, mobile, status, order_no, "
    "title, value_fen, detail_json, source, occurred_at, created_at, template_id, "
    "valid_from, valid_until, cycle_no "
    "FROM coupon_inventory "
    "WHERE title = ? AND value_fen = ? AND template_id = ? "
    "ORDER BY id"
)

EXISTING_CONSUME_SQL = (
    "SELECT id, coupon_id, coupon_group_id, customer_id, mobile, status, order_no, "
    "title, value_fen, detail_json, source, occurred_at, created_at, template_id, "
    "valid_from, valid_until, consumed_at, cycle_no "
    "FROM coupon_inventory "
    "WHERE coupon_id = ? AND mobile = ? AND status = ? "
    "ORDER BY cycle_no DESC, id DESC LIMIT 1"
)

UPDATE_ROW_SQL = (
    "UPDATE coupon_inventory "
    "SET coupon_group_id = ?, title = ?, value_fen = ?, template_id = ?, "
    "valid_from = ?, valid_until = ?, detail_json = ? "
    "WHERE id = ? AND coupon_id = ? AND mobile = ? "
    "AND title = ? AND value_fen = ? AND template_id = ?"
)

UPDATE_CONSUME_SQL = (
    "UPDATE coupon_inventory "
    "SET coupon_group_id = ?, title = ?, value_fen = ?, template_id = ?, "
    "valid_from = ?, valid_until = ?, order_no = ?, occurred_at = ?, consumed_at = ?, "
    "detail_json = ? "
    "WHERE id = ? AND coupon_id = ? AND mobile = ? AND status = ?"
)

INSERT_CONSUME_SQL = (
    "INSERT INTO coupon_inventory (coupon_id, coupon_group_id, customer_id, mobile, "
    "status, order_no, title, value_fen, detail_json, source, occurred_at, created_at, "
    "template_id, valid_from, valid_until, deducted_fen, consumed_at, refunded_at, "
    "cycle_no) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

BUSINESS_TIMEOUT_MS = 15000

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REJECTED = 2

# 日志统一走 stderr，保证 stdout 只有一份可被机器解析的 JSON 报告。
logger = logging.getLogger("yunxi_bot.reconcile_coupon_status")
logger.propagate = False


class TargetRejected(Exception):
    """目标库或运行前提不满足安全约束。"""


class ReconcileFailed(Exception):
    """对账落库过程中存在失败行，需整体回滚。"""


@dataclass(frozen=True)
class CouponRow:
    """一条本地券库存行。"""

    row_id: int
    coupon_id: str
    coupon_group_id: str
    customer_id: str
    mobile: str
    status: str
    order_no: str
    title: str
    value_fen: int
    detail_json: str
    source: str
    occurred_at: str
    created_at: str
    template_id: str
    valid_from: str
    valid_until: str
    cycle_no: int


@dataclass(frozen=True)
class YouzanFact:
    """有赞侧一张券的当前事实。"""

    coupon_id: str
    status: str
    group_id: str
    raw: dict


@dataclass
class Decision:
    """单行对账结论与待执行动作。"""

    row: CouponRow
    category: str
    reason: str
    action: str = ACTION_KEEP
    fields: dict[str, object] = field(default_factory=dict)
    note: str = ""


@dataclass
class ApplyOutcome:
    """一次写库执行的结果。"""

    inserted_ids: list[int] = field(default_factory=list)
    updated_ids: list[int] = field(default_factory=list)
    aligned_ids: list[int] = field(default_factory=list)
    failures: list[dict[str, object]] = field(default_factory=list)
    committed: bool = False
    error: str = ""


class YouzanCouponProbe:
    """有赞券现状探针。

    两路数据互补，缺一不可：

    - `list_merged`：复用已修复的 `YouzanMemberApi.list_customer_coupons`
      （按 `VALID/USED/INVALID` 三状态合并去重），能拿到「当前有效」与「已使用」；
    - `list_invalid`：按 `INVALID` 状态原样查询，**包含合并查询会过滤掉的
      「已失效且未使用」券**——过期券对账只能靠它，否则会被误判成「查不到」。

    `list_invalid` 复用 `YouzanMemberApi` 已固定的接口名与版本常量，不另造
    契约；响应体的券数组解析在本脚本内独立实现（形状兼容 `data`/`response`
    直接是数组与 `{cards|codes|coupons|list: [...]}` 两种）。
    """

    def __init__(self, member_api, client) -> None:
        self._member_api = member_api
        self._client = client

    async def list_merged(self, mobile: str) -> list[dict]:
        """拉取客户当前持有的券（合并态）。"""
        coupons = await self._member_api.list_customer_coupons(mobile)
        return [item for item in (coupons or []) if isinstance(item, dict)]

    async def list_invalid(self, mobile: str) -> list[dict]:
        """按 INVALID 状态原样拉取券（含已失效且未使用的券）。"""
        items: list[dict] = []
        for api_name, version in (
            (COUPON_LIST_API_NAME, COUPON_LIST_API_VERSION),
            (COUPON_CODE_LIST_API_NAME, COUPON_CODE_LIST_API_VERSION),
        ):
            result = await self._client.call_api(
                api_name,
                version,
                {
                    "kdt_id": settings.YOUZAN_KDT_ID,
                    "mobile": mobile,
                    "status": COUPON_STATUS_INVALID,
                },
            )
            items.extend(_extract_coupon_items(result))
        return items

    async def get_group_detail(self, coupon_group_id: str) -> dict:
        """查询券模板详情（面额与活动有效期的来源）。"""
        if not coupon_group_id:
            return {}
        detail = await self._member_api.get_coupon_group_detail(coupon_group_id)
        return detail if isinstance(detail, dict) else {}


def _extract_coupon_items(result: object) -> list[dict]:
    """从有赞响应中提取券数组（兼容两种响应形状）。"""
    if not isinstance(result, dict):
        return []
    for container in (result.get("data"), result.get("response")):
        if isinstance(container, list):
            return [item for item in container if isinstance(item, dict)]
        if not isinstance(container, dict):
            continue
        for key in ("cards", "codes", "coupons", "list"):
            items = container.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    return []


def _configure_logging() -> None:
    """初始化脚本日志器，输出到 stderr。"""
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(levelname)s  %(name)s  %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def format_beijing(moment: datetime) -> str:
    """把时间格式化成库内统一的字符串格式。"""
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def today_text() -> str:
    """今天的日期（北京时间，YYYY-MM-DD）。"""
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")


def evaluate_target_guard(
    db_path: Path, *, allow_production: bool
) -> dict[str, object]:
    """校验目标库路径，返回防呆结论；不满足前提时抛 TargetRejected。"""
    production_like = looks_like_production_path(str(db_path))
    if production_like and not allow_production:
        raise TargetRejected(
            f"目标库路径疑似生产部署目录（{db_path}），"
            "必须显式传 --allow-production 才能继续"
        )
    if not db_path.is_file():
        raise TargetRejected(f"目标库文件不存在: {db_path}（本脚本不会创建数据库）")
    return {
        "production_like": production_like,
        "allow_production": allow_production,
    }


def _connect(db_path: Path, *, read_only: bool) -> sqlite3.Connection:
    """打开目标库；dry-run 一律只读打开，避免任何意外写入。"""
    timeout_seconds = BUSINESS_TIMEOUT_MS / 1000
    if read_only:
        return sqlite3.connect(
            f"{db_path.resolve().as_uri()}?mode=ro",
            uri=True,
            timeout=timeout_seconds,
            isolation_level=None,
        )
    return sqlite3.connect(str(db_path), timeout=timeout_seconds, isolation_level=None)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    """判断目标库是否具备指定表。"""
    row = connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row and int(row[0]) > 0)


def _column_exists(
    connection: sqlite3.Connection, table_name: str, column_name: str
) -> bool:
    """判断目标表是否具备指定列。"""
    row = connection.execute(
        "SELECT COUNT(*) FROM pragma_table_info(?) WHERE name = ?",
        (table_name, column_name),
    ).fetchone()
    return bool(row and int(row[0]) > 0)


def fetch_target_rows(connection: sqlite3.Connection) -> list[CouponRow]:
    """读取全部骨架券行（按 id 升序，保证报告稳定）。"""
    rows = connection.execute(
        TARGET_ROWS_SQL, (STALE_TITLE, STALE_VALUE_FEN, STALE_TEMPLATE_ID)
    ).fetchall()
    return [
        CouponRow(
            row_id=int(row[0]),
            coupon_id=str(row[1] or ""),
            coupon_group_id=str(row[2] or ""),
            customer_id=str(row[3] or ""),
            mobile=str(row[4] or ""),
            status=str(row[5] or ""),
            order_no=str(row[6] or ""),
            title=str(row[7] or ""),
            value_fen=int(row[8] or 0),
            detail_json=str(row[9] or "{}"),
            source=str(row[10] or ""),
            occurred_at=str(row[11] or ""),
            created_at=str(row[12] or ""),
            template_id=str(row[13] or ""),
            valid_from=str(row[14] or ""),
            valid_until=str(row[15] or ""),
            cycle_no=int(row[16] or 0),
        )
        for row in rows
    ]


def fetch_existing_consume(
    connection: sqlite3.Connection, coupon_id: str, mobile: str
) -> dict | None:
    """读取该券已有的 CONSUME 行（幂等判定的唯一依据）。"""
    row = connection.execute(
        EXISTING_CONSUME_SQL, (coupon_id, mobile, LOCAL_STATUS_CONSUME)
    ).fetchone()
    if row is None:
        return None
    return {
        "id": int(row[0]),
        "coupon_id": str(row[1] or ""),
        "coupon_group_id": str(row[2] or ""),
        "customer_id": str(row[3] or ""),
        "mobile": str(row[4] or ""),
        "status": str(row[5] or ""),
        "order_no": str(row[6] or ""),
        "title": str(row[7] or ""),
        "value_fen": int(row[8] or 0),
        "detail_json": str(row[9] or "{}"),
        "source": str(row[10] or ""),
        "occurred_at": str(row[11] or ""),
        "created_at": str(row[12] or ""),
        "template_id": str(row[13] or ""),
        "valid_from": str(row[14] or ""),
        "valid_until": str(row[15] or ""),
        "consumed_at": str(row[16] or ""),
        "cycle_no": int(row[17] or 0),
    }


def _safe_int(value: object) -> int:
    """容忍转换整数，失败返回 0。"""
    if value is None:
        return 0
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def _coupon_id_of(raw: dict) -> str:
    """取券 ID（有赞两种字段名都可能出现）。"""
    return str(raw.get("coupon_id") or raw.get("id") or "")


def _is_used(raw: dict) -> bool:
    """判断有赞券是否已被使用。"""
    return _safe_int(raw.get("is_used")) == 1


def build_facts(merged: list[dict], invalid: list[dict]) -> dict[str, YouzanFact]:
    """把有赞两路返回合并成「券 ID → 当前事实」索引。

    合并查询里 `is_used=1` 的券一律按「已使用」认定：上游 `INVALID` 返回集也
    包含已使用的券，若照抄标签会把已核销事实误判成「已失效未使用」。
    """
    facts: dict[str, YouzanFact] = {}
    for raw in merged:
        coupon_id = _coupon_id_of(raw)
        if not coupon_id:
            continue
        tag = str(raw.get("youzan_coupon_status") or "").strip().upper()
        if _is_used(raw):
            status = YOZAN_USED
        elif tag == YOZAN_VALID:
            status = YOZAN_VALID
        elif tag == YOZAN_INVALID:
            status = YOZAN_INVALID
        else:
            status = YOZAN_UNKNOWN
        facts[coupon_id] = YouzanFact(
            coupon_id=coupon_id,
            status=status,
            group_id=str(raw.get("coupon_group_id") or ""),
            raw=raw,
        )
    for raw in invalid:
        coupon_id = _coupon_id_of(raw)
        if not coupon_id or coupon_id in facts:
            continue
        facts[coupon_id] = YouzanFact(
            coupon_id=coupon_id,
            status=YOZAN_USED if _is_used(raw) else YOZAN_INVALID,
            group_id=str(raw.get("coupon_group_id") or ""),
            raw=raw,
        )
    return facts


def _extract_used_at(raw: dict) -> str:
    """取有赞券的核销时间（毫秒时间戳，转北京时间字符串）。"""
    for key in ("used_at", "use_at", "used_time", "consume_at", "used_at_ms"):
        value = raw.get(key)
        if value in (None, ""):
            continue
        text = format_millis_datetime(value)
        if text:
            return text
    return ""


async def _resolve_metadata(
    row: CouponRow, fact: YouzanFact, probe: YouzanCouponProbe
) -> dict[str, object]:
    """取有赞券模板并解析出要落库的元数据。"""
    group_id = fact.group_id or row.coupon_group_id
    detail = await probe.get_group_detail(group_id) if group_id else {}
    template = parse_youzan_template(detail)
    fields = extract_template_fields(fact.raw, detail)
    title = str(
        fact.raw.get("title") or fact.raw.get("coupon_name") or template.name or ""
    )
    value_fen = template.value_fen or to_fen(
        fact.raw.get("value") or fact.raw.get("amount") or fact.raw.get("coupon_value")
    )
    return {
        "coupon_group_id": group_id or row.coupon_group_id,
        "title": title,
        "value_fen": value_fen,
        "template_id": str(fields.get("template_id", "")),
        "valid_from": str(fields.get("valid_from", "")),
        "valid_until": str(fields.get("valid_until", "")),
        "detail_json": json.dumps(fact.raw, ensure_ascii=False),
    }


def _decide_used(
    row: CouponRow,
    fact: YouzanFact,
    metadata: dict[str, object],
    connection: sqlite3.Connection,
) -> Decision:
    """本地持有 + 有赞已使用：生成本地 CONSUME 事实。"""
    if not str(metadata.get("title", "")):
        return Decision(
            row,
            CATEGORY_KEPT,
            REASON_TITLE_MISSING,
            note="有赞未给出券名，无法补全核销事实",
        )
    order_no = str(fact.raw.get("used_in_order_no") or fact.raw.get("order_no") or "")
    used_at = (
        _extract_used_at(fact.raw)
        or format_millis_datetime(fact.raw.get("take_at"))
        or row.occurred_at
    )
    # 本地 TAKE 行的 occurred_at 是「有赞事件到达时间」（Webhook 落库口径），往往
    # 晚于券的真实核销时间。最新状态解析按 occurred_at 倒序取行，照搬核销时间
    # 会让最新状态退回 TAKE，券重新变成可用券（资损）。因此事实行时间取两者
    # 较晚者；真实核销时间保留在 consumed_at 与 youzan_used_at 里。
    occurred_at = max(used_at, row.occurred_at)
    note = "有赞已核销，新增本地 CONSUME 事实行"
    if occurred_at != used_at:
        note = (
            "有赞已核销，新增本地 CONSUME 事实行；本地 TAKE 行的事件时间晚于核销时间，"
            "事实行时间取较晚者，确保最新状态为 CONSUME"
        )
    fields = {
        **metadata,
        "order_no": order_no,
        "occurred_at": occurred_at,
        "consumed_at": used_at,
        "used_at": used_at,
    }
    if row.status == LOCAL_STATUS_CONSUME:
        return Decision(
            row,
            CATEGORY_CONSUME_METADATA,
            REASON_USED_CONSUME_METADATA,
            ACTION_UPDATE_CONSUME,
            fields,
            note="本地已是 CONSUME，只补全元数据",
        )
    existing = fetch_existing_consume(connection, row.coupon_id, row.mobile)
    if existing is not None:
        # 幂等：CONSUME 事实已存在（重复执行），只补全元数据，绝不重复插入
        return Decision(
            row,
            CATEGORY_CONSUME_ALIGNED,
            REASON_USED_EXISTING,
            ACTION_UPDATE_CONSUME,
            fields,
            note="本地已有 CONSUME 事实行，只补全元数据",
        )
    return Decision(
        row,
        CATEGORY_CONSUME_INSERTED,
        REASON_USED_CONFLICT,
        ACTION_INSERT_CONSUME,
        fields,
        note=note,
    )


def _decide_invalid(
    row: CouponRow, fact: YouzanFact, metadata: dict[str, object], today: str
) -> Decision:
    """本地持有 + 有赞已失效未使用：按过期拒绝，不写成可用券。"""
    if row.status == LOCAL_STATUS_CONSUME:
        return Decision(
            row,
            CATEGORY_KEPT,
            REASON_STATUS_CONFLICT,
            note="local=CONSUME youzan=INVALID（未使用），两侧事实矛盾，保留原行",
        )
    valid_until = str(metadata.get("valid_until", ""))
    if not valid_until:
        return Decision(
            row,
            CATEGORY_KEPT,
            REASON_EXPIRY_UNPROVABLE,
            note="有赞未给出券过期时间，只补面额会让过期券变可用，保留原行",
        )
    if valid_until[:10] >= today:
        return Decision(
            row,
            CATEGORY_KEPT,
            REASON_EXPIRY_UNPROVABLE,
            note=f"券过期时间不早于今天（valid_until={valid_until}），保留原行",
        )
    return Decision(
        row,
        CATEGORY_EXPIRED_FILLED,
        REASON_INVALID_EXPIRED,
        ACTION_UPDATE_ROW,
        {**metadata, "valid_until": valid_until},
        note="有赞已失效未使用，按券自身过期时间补全后由本地引擎拒绝",
    )


def _decide_valid(
    row: CouponRow, fact: YouzanFact, metadata: dict[str, object]
) -> Decision:
    """本地持有 + 有赞当前有效：两侧一致，只补全元数据。"""
    if row.status == LOCAL_STATUS_CONSUME:
        return Decision(
            row,
            CATEGORY_KEPT,
            REASON_STATUS_CONFLICT,
            note="local=CONSUME youzan=VALID，两侧事实矛盾，保留原行",
        )
    if not str(metadata.get("title", "")):
        return Decision(
            row,
            CATEGORY_KEPT,
            REASON_TITLE_MISSING,
            note="有赞未给出券名，保留原行",
        )
    return Decision(
        row,
        CATEGORY_VALID_ALIGNED,
        REASON_VALID_ALIGNED,
        ACTION_UPDATE_ROW,
        metadata,
        note="有赞当前有效，与本地持有事实一致",
    )


async def decide_row(
    row: CouponRow,
    fact: YouzanFact | None,
    probe: YouzanCouponProbe,
    today: str,
    connection: sqlite3.Connection,
) -> Decision:
    """判定单条骨架券行能否落库，并给出待写入动作。"""
    if not row.coupon_id:
        return Decision(row, CATEGORY_KEPT, REASON_COUPON_ID_MISSING)
    if not row.mobile:
        return Decision(row, CATEGORY_KEPT, REASON_MOBILE_MISSING)
    if fact is None:
        return Decision(row, CATEGORY_KEPT, REASON_NOT_FOUND)
    if row.status not in (LOCAL_STATUS_TAKE, LOCAL_STATUS_CONSUME):
        return Decision(
            row,
            CATEGORY_KEPT,
            REASON_LOCAL_STATUS_UNSUPPORTED,
            note=f"local={row.status or '(empty)'}",
        )
    if fact.status == YOZAN_UNKNOWN:
        return Decision(
            row,
            CATEGORY_KEPT,
            REASON_STATUS_CONFLICT,
            note="有赞券状态无法归类，保留原行",
        )
    metadata = await _resolve_metadata(row, fact, probe)
    if fact.status == YOZAN_USED:
        return _decide_used(row, fact, metadata, connection)
    if fact.status == YOZAN_INVALID:
        return _decide_invalid(row, fact, metadata, today)
    return _decide_valid(row, fact, metadata)


async def _fetch_facts(
    probe: YouzanCouponProbe, mobile: str
) -> tuple[dict[str, YouzanFact], str]:
    """拉取某手机号的有赞券现状；失败时返回空索引与错误说明。"""
    try:
        merged = await probe.list_merged(mobile)
        invalid = await probe.list_invalid(mobile)
    except Exception as exc:
        logger.error(
            "有赞券现状查询失败 mobile=%s err=%s: %s",
            mask_sensitive(mobile),
            type(exc).__name__,
            exc,
        )
        return {}, mask_sensitive(f"{type(exc).__name__}: {exc}")
    return build_facts(merged, invalid), ""


async def plan_reconcile(
    rows: list[CouponRow], probe: YouzanCouponProbe, connection: sqlite3.Connection
) -> list[Decision]:
    """按手机号去重向有赞核对，给出每条骨架券行的对账结论。"""
    decisions: list[Decision] = []
    today = today_text()
    rows_by_mobile: dict[str, list[CouponRow]] = {}
    for row in rows:
        rows_by_mobile.setdefault(row.mobile, []).append(row)
    for mobile, mobile_rows in rows_by_mobile.items():
        facts, error = await _fetch_facts(probe, mobile)
        for row in mobile_rows:
            if error:
                decisions.append(
                    Decision(row, CATEGORY_KEPT, REASON_QUERY_FAILED, note=error)
                )
                continue
            decisions.append(
                await decide_row(
                    row, facts.get(row.coupon_id), probe, today, connection
                )
            )
    return decisions


def _prefer_existing(existing: object, new: object) -> object:
    """已有值非空时保留既有值：只补空缺，不覆盖既有事实。"""
    if isinstance(existing, bool):
        return existing
    if isinstance(existing, (int, float)):
        return existing if int(existing) != 0 else new
    return existing if str(existing or "") else new


def _merge_fields(existing: dict, fields: dict[str, object]) -> dict[str, object]:
    """把新解析出的字段与既有 CONSUME 行合并（既有值优先）。"""
    merged = dict(fields)
    for key in (
        "coupon_group_id",
        "title",
        "value_fen",
        "template_id",
        "valid_from",
        "valid_until",
        "order_no",
        "occurred_at",
        "consumed_at",
    ):
        merged[key] = _prefer_existing(existing.get(key, ""), fields.get(key, ""))
    return merged


def _insert_consume_row(
    connection: sqlite3.Connection, decision: Decision, now: str
) -> None:
    """新增一条本地 CONSUME 事实行。"""
    row = decision.row
    fields = decision.fields
    cursor = connection.execute(
        INSERT_CONSUME_SQL,
        (
            row.coupon_id,
            str(fields.get("coupon_group_id", "")),
            row.customer_id,
            row.mobile,
            LOCAL_STATUS_CONSUME,
            str(fields.get("order_no", "")),
            str(fields.get("title", "")),
            int(fields.get("value_fen", 0) or 0),
            str(fields.get("detail_json", "{}")),
            SOURCE_IMPORT,
            str(fields.get("occurred_at", "")),
            now,
            str(fields.get("template_id", "")),
            str(fields.get("valid_from", "")),
            str(fields.get("valid_until", "")),
            0,
            str(fields.get("consumed_at", "")),
            "",
            row.cycle_no,
        ),
    )
    if int(cursor.rowcount or 0) != 1:
        raise ReconcileFailed(f"券 {row.coupon_id} 的 CONSUME 事实写入异常")


def _update_consume_row(
    connection: sqlite3.Connection, decision: Decision, existing: dict
) -> bool:
    """补全既有 CONSUME 行的元数据（不重复插入、不改状态）。

    返回是否真的写库：合并后与既有行完全一致时**不写**（重复执行时保持
    真正的空操作，不产生无意义的行改写）。
    """
    row = decision.row
    fields = _merge_fields(existing, decision.fields)
    changed = any(
        str(fields.get(key, "")) != str(existing.get(key, ""))
        for key in (
            "coupon_group_id",
            "title",
            "value_fen",
            "template_id",
            "valid_from",
            "valid_until",
            "order_no",
            "occurred_at",
            "consumed_at",
        )
    ) or str(fields.get("detail_json", "{}")) != str(existing.get("detail_json", "{}"))
    if not changed:
        return False
    cursor = connection.execute(
        UPDATE_CONSUME_SQL,
        (
            str(fields.get("coupon_group_id", "")),
            str(fields.get("title", "")),
            int(fields.get("value_fen", 0) or 0),
            str(fields.get("template_id", "")),
            str(fields.get("valid_from", "")),
            str(fields.get("valid_until", "")),
            str(fields.get("order_no", "")),
            str(fields.get("occurred_at", "")),
            str(fields.get("consumed_at", "")),
            str(fields.get("detail_json", "{}")),
            int(existing["id"]),
            row.coupon_id,
            row.mobile,
            LOCAL_STATUS_CONSUME,
        ),
    )
    if int(cursor.rowcount or 0) != 1:
        raise ReconcileFailed(f"券 {row.coupon_id} 的 CONSUME 元数据更新命中数异常")
    return True


def _update_target_row(connection: sqlite3.Connection, decision: Decision) -> None:
    """补全骨架券行的元数据（状态不变，仍是 TAKE）。"""
    row = decision.row
    fields = decision.fields
    cursor = connection.execute(
        UPDATE_ROW_SQL,
        (
            str(fields.get("coupon_group_id", "")),
            str(fields.get("title", "")),
            int(fields.get("value_fen", 0) or 0),
            str(fields.get("template_id", "")),
            str(fields.get("valid_from", "")),
            str(fields.get("valid_until", "")),
            str(fields.get("detail_json", "{}")),
            row.row_id,
            row.coupon_id,
            row.mobile,
            STALE_TITLE,
            STALE_VALUE_FEN,
            STALE_TEMPLATE_ID,
        ),
    )
    if int(cursor.rowcount or 0) != 1:
        raise ReconcileFailed(
            f"骨架券行 {row.row_id} 更新命中数异常（可能已被并发修改），事务整体回滚"
        )


def apply_reconcile(
    connection: sqlite3.Connection, decisions: list[Decision]
) -> ApplyOutcome:
    """在单个事务内落库；任一行失败整体回滚。"""
    outcome = ApplyOutcome()
    writes = [item for item in decisions if item.action != ACTION_KEEP]
    if not writes:
        return outcome
    now = now_str()
    connection.execute("BEGIN IMMEDIATE")
    try:
        for decision in writes:
            if decision.action == ACTION_INSERT_CONSUME:
                existing = fetch_existing_consume(
                    connection, decision.row.coupon_id, decision.row.mobile
                )
                if existing is None:
                    _insert_consume_row(connection, decision, now)
                    outcome.inserted_ids.append(decision.row.row_id)
                else:
                    # 幂等：CONSUME 行已存在（重复执行），只补全元数据
                    changed = _update_consume_row(connection, decision, existing)
                    if changed:
                        outcome.updated_ids.append(decision.row.row_id)
                    else:
                        outcome.aligned_ids.append(decision.row.row_id)
            elif decision.action == ACTION_UPDATE_CONSUME:
                existing = fetch_existing_consume(
                    connection, decision.row.coupon_id, decision.row.mobile
                )
                if existing is None:
                    raise ReconcileFailed(
                        f"券 {decision.row.coupon_id} 的本地 CONSUME 行不存在，"
                        "事务整体回滚"
                    )
                changed = _update_consume_row(connection, decision, existing)
                if changed:
                    outcome.updated_ids.append(decision.row.row_id)
                else:
                    outcome.aligned_ids.append(decision.row.row_id)
            else:
                _update_target_row(connection, decision)
                outcome.updated_ids.append(decision.row.row_id)
        connection.execute("COMMIT")
        outcome.committed = True
    except Exception as exc:
        connection.execute("ROLLBACK")
        outcome.inserted_ids = []
        outcome.updated_ids = []
        outcome.aligned_ids = []
        outcome.failures.append({"reason": str(exc)})
        outcome.error = f"写库失败已回滚: {exc}"
        logger.error("券状态对账写库失败已整体回滚: %s", exc)
    return outcome


def _count_by(decisions: list[Decision], key: str) -> dict[str, int]:
    """按分类或原因分组计数，结果按键排序。"""
    counts: dict[str, int] = {}
    for item in decisions:
        value = getattr(item, key) or ""
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _count_rows_by(rows: list[CouponRow], key: str) -> dict[str, int]:
    """按骨架券行的字段分组计数，结果按键排序。"""
    counts: dict[str, int] = {}
    for row in rows:
        value = str(getattr(row, key) or "") or "(empty)"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _decision_row(decision: Decision) -> dict[str, object]:
    """把单条对账结论转成脱敏后的报告条目。"""
    row = decision.row
    fields = decision.fields
    return {
        "id": row.row_id,
        "coupon_id": row.coupon_id,
        "mobile": mask_sensitive(row.mobile),
        "local_status": row.status or "(empty)",
        "local_source": row.source or "(empty)",
        "category": decision.category,
        "reason": decision.reason,
        "reason_text": REASON_TEXT.get(decision.reason, ""),
        "action": decision.action,
        "note": decision.note,
        "order_no": str(fields.get("order_no", "")) if fields else "",
        "youzan_used_at": str(fields.get("used_at", "")) if fields else "",
        "new_title": str(fields.get("title", "")) if fields else "",
        "new_value_fen": int(fields.get("value_fen", 0) or 0) if fields else 0,
        "new_template_id": str(fields.get("template_id", "")) if fields else "",
        "new_valid_from": str(fields.get("valid_from", "")) if fields else "",
        "new_valid_until": str(fields.get("valid_until", "")) if fields else "",
        "new_occurred_at": str(fields.get("occurred_at", "")) if fields else "",
    }


def build_report(
    rows: list[CouponRow],
    decisions: list[Decision],
    outcome: ApplyOutcome,
    *,
    mode: str,
    db_path: str,
    guard: dict[str, object],
) -> dict[str, object]:
    """生成稳定结构的对账报告。"""
    by_category = _count_by(decisions, "category")
    by_reason = _count_by(decisions, "reason")
    by_action = _count_by(decisions, "action")
    status_by_category: dict[str, int] = {}
    for item in decisions:
        label = f"{item.category}:{item.row.status or '(empty)'}"
        status_by_category[label] = status_by_category.get(label, 0) + 1
    kept = by_category.get(CATEGORY_KEPT, 0)
    return {
        "status": "failed" if outcome.error else "ok",
        "mode": mode,
        "db": db_path,
        "run_at": format_beijing(datetime.now(BEIJING_TZ)),
        "production_guard": guard,
        "scope": {
            "target_total": len(rows),
            "distinct_mobiles": len({row.mobile for row in rows}),
            "by_status": _count_rows_by(rows, "status"),
            "by_source": _count_rows_by(rows, "source"),
            "by_coupon_group_id": _count_rows_by(rows, "coupon_group_id"),
        },
        "stats": {
            "by_category": by_category,
            "by_reason": by_reason,
            "by_action": by_action,
            "by_category_and_local_status": dict(sorted(status_by_category.items())),
        },
        "plan": {
            "would_insert_consume": by_action.get(ACTION_INSERT_CONSUME, 0),
            "would_update_consume": by_action.get(ACTION_UPDATE_CONSUME, 0),
            "would_update_row": by_action.get(ACTION_UPDATE_ROW, 0),
            "would_keep": kept,
        },
        "result": {
            "inserted": len(outcome.inserted_ids),
            "inserted_ids": outcome.inserted_ids,
            "updated": len(outcome.updated_ids),
            "updated_ids": outcome.updated_ids,
            "aligned": len(outcome.aligned_ids),
            "aligned_ids": outcome.aligned_ids,
            "failures": outcome.failures,
            "committed": outcome.committed,
            "error": outcome.error,
        },
        "rows": [_decision_row(item) for item in decisions],
        "summary": {
            "target_total": len(rows),
            "consume_fact_inserted": by_category.get(CATEGORY_CONSUME_INSERTED, 0),
            "consume_fact_aligned": by_category.get(CATEGORY_CONSUME_ALIGNED, 0),
            "consume_metadata_filled": by_category.get(CATEGORY_CONSUME_METADATA, 0),
            "expired_filled": by_category.get(CATEGORY_EXPIRED_FILLED, 0),
            "valid_aligned": by_category.get(CATEGORY_VALID_ALIGNED, 0),
            "kept": kept,
            "inserted": len(outcome.inserted_ids),
            "updated": len(outcome.updated_ids),
            "aligned": len(outcome.aligned_ids),
            "committed": outcome.committed,
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数；默认 dry-run，不写库。"""
    parser = argparse.ArgumentParser(
        description="对账 coupon_inventory 骨架券行与有赞当前券状态"
    )
    parser.add_argument("--db", required=True, help="目标 SQLite 数据库路径（必填）")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写库；不加该参数时只做只读核对。",
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="允许对疑似生产路径的数据库执行操作。",
    )
    parser.add_argument("--output", default="", help="把 JSON 报告额外写入指定文件")
    return parser.parse_args(argv)


def emit_report(report: dict[str, object], output_path: str) -> None:
    """把报告写到 stdout，并按需额外落盘。"""
    text = json.dumps(report, ensure_ascii=False, indent=2)
    sys.stdout.write(text + "\n")
    if not output_path:
        return
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    logger.info("报告已写入 %s", path)


async def run_reconcile(
    db_path: Path,
    probe: YouzanCouponProbe,
    *,
    should_apply: bool,
) -> tuple[list[CouponRow], list[Decision], ApplyOutcome]:
    """在目标库上完成对账（可选落库）并返回判定结论。"""
    with closing(_connect(db_path, read_only=not should_apply)) as connection:
        if not _table_exists(connection, "coupon_inventory"):
            raise sqlite3.OperationalError("目标库缺少 coupon_inventory 表")
        if not _column_exists(connection, "coupon_inventory", "template_id"):
            raise sqlite3.OperationalError(
                "目标库 coupon_inventory 缺少 template_id 列"
            )
        rows = fetch_target_rows(connection)
        decisions = await plan_reconcile(rows, probe, connection)
        outcome = ApplyOutcome()
        if should_apply:
            outcome = apply_reconcile(connection, decisions)
        return rows, decisions, outcome


def build_probe() -> tuple[YouzanCouponProbe, object]:
    """构造真实的有赞券现状探针，返回 (探针, 底层云客户端)。"""
    from app.service.youzan.client import YouzanClient
    from app.service.youzan.member_api import YouzanMemberApi

    client = YouzanClient()
    return YouzanCouponProbe(YouzanMemberApi(client), client), client


async def async_main(
    argv: list[str] | None = None, probe: YouzanCouponProbe | None = None
) -> int:
    """脚本主流程：对账（可选落库）并输出报告。

    `probe` 只在测试里注入假的有赞客户端；缺省时构造真实客户端。
    """
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report: dict[str, object] = {
        "status": "ok",
        "mode": "apply" if args.apply else "dry-run",
        "db": str(args.db),
    }
    try:
        db_path = Path(args.db).expanduser()
        guard = evaluate_target_guard(
            db_path, allow_production=bool(args.allow_production)
        )
    except TargetRejected as exc:
        report["status"] = "rejected"
        report["error"] = str(exc)
        report["summary"] = {"rejected": True}
        emit_report(report, args.output)
        logger.error("目标库被拒绝: %s", exc)
        return EXIT_REJECTED

    report["production_guard"] = guard
    client = None
    try:
        if probe is None:
            if settings.YOUZAN_MOCK_MODE:
                raise TargetRejected(
                    "有赞 Mock 模式开启，拒绝执行券状态对账（拿不到真实券状态）"
                )
            probe, client = build_probe()
        rows, decisions, outcome = await run_reconcile(
            db_path, probe, should_apply=bool(args.apply)
        )
    except TargetRejected as exc:
        report["status"] = "rejected"
        report["error"] = str(exc)
        report["summary"] = {"rejected": True}
        emit_report(report, args.output)
        logger.error("对账被拒绝: %s", exc)
        return EXIT_REJECTED
    except sqlite3.Error as exc:
        logger.error("数据库操作失败: %s", exc)
        report["status"] = "failed"
        report["error"] = f"数据库操作失败: {exc}"
        emit_report(report, args.output)
        return EXIT_FAILED
    finally:
        if client is not None:
            await client.close()

    report.update(
        build_report(
            rows,
            decisions,
            outcome,
            mode="apply" if args.apply else "dry-run",
            db_path=str(args.db),
            guard=guard,
        )
    )
    emit_report(report, args.output)
    summary = report.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    logger.info(
        "券状态对账完成 mode=%s target=%s consume_inserted=%s expired_filled=%s "
        "kept=%s inserted=%s committed=%s",
        report["mode"],
        summary.get("target_total", 0),
        summary.get("consume_fact_inserted", 0),
        summary.get("expired_filled", 0),
        summary.get("kept", 0),
        summary.get("inserted", 0),
        summary.get("committed", False),
    )
    if outcome.error:
        logger.error("券状态对账未完成: %s", outcome.error)
        return EXIT_FAILED
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """脚本入口，返回进程退出码。"""
    _configure_logging()
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
