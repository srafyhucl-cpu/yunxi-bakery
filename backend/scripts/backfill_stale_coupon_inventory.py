"""旧券库存定向回填：用有赞当前券数据补全 coupon_inventory 的券名字段。

背景
----
2026-10-20 券/卡 API 契约修复上线前，有赞「查询买家优惠券列表」用错了接口名
（`youzan.ump.coupon.user.coupons` 在开放平台并不存在，网关一律以 4005 拒绝），
`youzan.ump.coupon.detail.get` 的请求参数也传错（传 `coupon_group_id` 而非
`id`，被判 161201012）。于是当天入库的优惠券 Webhook 事件在反查券模板时
恒定拿到空模板，写进 `coupon_inventory` 的行只有骨架：

    title=''  value_fen=0  template_id=''  valid_from=''  valid_until=''

生产实测（schema v48）：`coupon_inventory` 共 69 行，**全部**是这种骨架行，
涉及 59 个手机号；`coupon_templates` 表 0 行。券的 `status` 已在上一步
归一（`CARD_TAKE→TAKE`、`CARD_CONSUME→CONSUME`），本次不动状态。

本脚本做什么
------------
按手机号去重调用当前已修复的 `YouzanMemberApi.list_customer_coupons(mobile)`
与 `get_coupon_group_detail(coupon_group_id)`，把有赞侧的事实回填到**同一
coupon_id + 同一 mobile** 的那一行上：券名、面额、券模板 ID、有效期、领券
时间与原始载荷。

本脚本不做什么
--------------
- 不删除任何行，不新建券行，不改动 `status` / `source` / `created_at`；
- 不按手机号批量改写别的券（更新条件里始终带 `coupon_id` 与 `mobile`）；
- 有赞侧查不到券、券状态映射不出来或券模板缺失时，**保留原行**并分类报告，
  绝不删除、绝不猜。

判定口径（只认有赞侧事实，不猜）
--------------------------------
- `backfilled`：有赞当前持有该券、状态可映射且与本地行状态一致、券模板可取
  → 回填券名/面额/模板/有效期/领券时间/载荷；
- `expired`：有赞侧已查不到该 `coupon_id`（客户当前不再持有，或已出查询
  窗口），或有赞返回的券状态无法映射到本地词表（上游 `INVALID` 等）→ 保留
  原行；
- `missing`：券模板缺失（拿不到面额与有效期）或券名缺失 → 保留原行；
- `ambiguous`：有赞状态与本地行状态冲突、同一 `coupon_id` 返回多条冲突载荷、
  手机号缺失、有赞接口调用失败 → 保留原行。

注意：有赞「已失效且未使用」的券**不**出现在买家券查询结果里，因此这类券在
本脚本里表现为 `expired/coupon_not_returned_by_youzan`，而不是有赞显式回���
`INVALID`。

安全约束
--------
- 必须显式传 `--db`，脚本不猜测任何默认库路径；
- 默认 dry-run（以 SQLite `mode=ro` 打开，全程只读），只有 `--apply` 才写库；
- 路径疑似生产部署目录时必须额外传 `--allow-production`；
- 写库在单个事务内完成，任一行失败整体回滚，绝不部分写入；
- 报告字段固定、手机号脱敏。

用法
----
    # 默认 dry-run：只出报告，不写库
    python scripts/backfill_stale_coupon_inventory.py --db /path/to/bot.db

    # 核对通过后回填（生产路径必须显式声明）
    python scripts/backfill_stale_coupon_inventory.py \
        --db /opt/apps/yunxi-bakery/backend/data/bot.db --apply --allow-production

    # 顺带把用到的有赞券模板同步进 coupon_templates（见下方「模板同步」）
    python scripts/backfill_stale_coupon_inventory.py \
        --db /opt/apps/yunxi-bakery/backend/data/bot.db --apply --allow-production \
        --upsert-templates

模板同步
--------
`coupon_templates` 当前是空表，券引擎算抵扣金额时取的是**模板**的
`coupon_type` / `threshold_fen` / `value_fen`（`app/service/coupon/rules.py`），
只回填 `coupon_inventory` 的话，券在结算页依旧算不出抵扣金额。因此本脚本
提供 `--upsert-templates`：只把「本次确实回填成功」的行所引用的那几个有赞
券模板 upsert 进 `coupon_templates`（幂等 ON CONFLICT DO UPDATE，口径与
`app/repository/coupon_template_repo.py` 一致），不建任何券行。该开关默认
关闭，需要显式打开。
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

from app.service.coupon.template_sync import (  # noqa: E402
    extract_template_fields,
    parse_youzan_template,
)
from app.service.youzan.member_helpers import map_coupon_status, to_fen  # noqa: E402
from app.utils import format_millis_datetime  # noqa: E402
from resolve_youzan_dead_letters import (  # noqa: E402
    looks_like_production_path,
    mask_sensitive,
)

# 骨架券行的判定条件：券名、面额、模板 ID 三者同时为空。
STALE_TITLE = ""
STALE_VALUE_FEN = 0
STALE_TEMPLATE_ID = ""

# 分类
CATEGORY_BACKFILLED = "backfilled"
CATEGORY_EXPIRED = "expired"
CATEGORY_MISSING = "missing"
CATEGORY_AMBIGUOUS = "ambiguous"

# 稳定原因码
REASON_COUPON_FOUND = "coupon_found"
REASON_COUPON_NOT_RETURNED = "coupon_not_returned_by_youzan"
REASON_STATUS_NOT_MAPPABLE = "youzan_status_not_mappable"
REASON_TEMPLATE_MISSING = "coupon_template_missing"
REASON_TITLE_MISSING = "coupon_title_missing"
REASON_STATUS_CONFLICT = "status_conflict_with_local_row"
REASON_DUPLICATE_PAYLOAD = "duplicate_coupon_payload"
REASON_MOBILE_MISSING = "mobile_missing"
REASON_COUPON_ID_MISSING = "coupon_id_missing"
REASON_YOUZAN_QUERY_FAILED = "youzan_query_failed"

REASON_TEXT = {
    REASON_COUPON_FOUND: "有赞当前持有该券且模板可取，可回填",
    REASON_COUPON_NOT_RETURNED: "有赞侧已查不到该券（已失效未使用或已出查询窗口）",
    REASON_STATUS_NOT_MAPPABLE: "有赞券状态无法映射到本地词表（上游已失效）",
    REASON_TEMPLATE_MISSING: "有赞券模板详情缺失，面额与有效期无从取得",
    REASON_TITLE_MISSING: "有赞券与模板都没有给出券名",
    REASON_STATUS_CONFLICT: "有赞券状态与本地行状态冲突，不改写",
    REASON_DUPLICATE_PAYLOAD: "同一 coupon_id 返回多条冲突载荷，不改写",
    REASON_MOBILE_MISSING: "行上没有手机号，无法向有赞核对",
    REASON_COUPON_ID_MISSING: "行上没有 coupon_id，无法向有赞核对",
    REASON_YOUZAN_QUERY_FAILED: "有赞接口调用失败，本行结论未知",
}

STALE_ROWS_SQL = (
    "SELECT id, coupon_id, coupon_group_id, customer_id, mobile, status, order_no, "
    "title, value_fen, detail_json, source, occurred_at, created_at, template_id, "
    "valid_from, valid_until, cycle_no "
    "FROM coupon_inventory "
    "WHERE title = ? AND value_fen = ? AND template_id = ? "
    "ORDER BY id"
)

BACKFILL_SQL = (
    "UPDATE coupon_inventory "
    "SET coupon_group_id = ?, title = ?, value_fen = ?, template_id = ?, "
    "valid_from = ?, valid_until = ?, occurred_at = ?, detail_json = ? "
    "WHERE id = ? AND coupon_id = ? AND mobile = ? "
    "AND title = ? AND value_fen = ? AND template_id = ?"
)

TEMPLATE_UPSERT_SQL = (
    "INSERT INTO coupon_templates (id, name, coupon_type, threshold_fen, value_fen, "
    "discount_bp, cap_fen, valid_from, valid_until, scope_json, status, source, "
    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
    "coupon_type=excluded.coupon_type, threshold_fen=excluded.threshold_fen, "
    "value_fen=excluded.value_fen, discount_bp=excluded.discount_bp, "
    "cap_fen=excluded.cap_fen, valid_from=excluded.valid_from, "
    "valid_until=excluded.valid_until, scope_json=excluded.scope_json, "
    "source=excluded.source, updated_at=excluded.updated_at"
)

BUSINESS_TIMEOUT_MS = 15000
SAMPLE_LIMIT = 20

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REJECTED = 2

# 日志统一走 stderr，保证 stdout 只有一份可被机器解析的 JSON 报告。
logger = logging.getLogger("yunxi_bot.backfill_stale_coupon_inventory")
logger.propagate = False


class TargetRejected(Exception):
    """目标库路径不满足安全前提。"""


class BackfillFailed(Exception):
    """回填过程中存在失败行，需整体回滚。"""


@dataclass(frozen=True)
class StaleCouponRow:
    """一条骨架券行（券名/面额/模板 ID 同时为空的旧行）。"""

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


@dataclass
class BackfillDecision:
    """单条骨架券行的判定结论与待写入字段。"""

    row: StaleCouponRow
    category: str
    reason: str
    fields: dict[str, object] = field(default_factory=dict)
    template: dict[str, object] = field(default_factory=dict)
    note: str = ""


@dataclass
class ApplyOutcome:
    """一次写库执行的结果。"""

    updated_ids: list[int] = field(default_factory=list)
    failures: list[dict[str, object]] = field(default_factory=list)
    templates_upserted: list[str] = field(default_factory=list)
    committed: bool = False
    error: str = ""


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


def fetch_stale_rows(connection: sqlite3.Connection) -> list[StaleCouponRow]:
    """读取全部骨架券行（按 id 升序，保证报告稳定）。"""
    rows = connection.execute(
        STALE_ROWS_SQL, (STALE_TITLE, STALE_VALUE_FEN, STALE_TEMPLATE_ID)
    ).fetchall()
    return [
        StaleCouponRow(
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


def _index_coupons(coupons: list[dict]) -> tuple[dict[str, dict], set[str]]:
    """把有赞买家券列表按券 ID 建索引，并标记同 ID 冲突的券。"""
    index: dict[str, dict] = {}
    conflicts: set[str] = set()
    for coupon in coupons:
        coupon_id = str(coupon.get("coupon_id") or coupon.get("id") or "")
        if not coupon_id:
            continue
        if coupon_id in index:
            if json.dumps(index[coupon_id], sort_keys=True) != json.dumps(
                coupon, sort_keys=True
            ):
                conflicts.add(coupon_id)
            continue
        index[coupon_id] = coupon
    return index, conflicts


async def _fetch_coupons(member_api, mobile: str) -> tuple[list[dict], str]:
    """拉取某手机号当前持有的有赞券；失败时返回空列表与错误说明。"""
    try:
        coupons = await member_api.list_customer_coupons(mobile)
    except Exception as exc:
        logger.error(
            "有赞买家券查询失败 mobile=%s err=%s: %s",
            mask_sensitive(mobile),
            type(exc).__name__,
            exc,
        )
        return [], mask_sensitive(f"{type(exc).__name__}: {exc}")
    return list(coupons or []), ""


async def _fetch_template_detail(
    member_api, group_id: str, cache: dict[str, dict]
) -> dict:
    """查询有赞券模板详情；同一券模板只查一次。"""
    if group_id in cache:
        return cache[group_id]
    detail = await member_api.get_coupon_group_detail(group_id)
    resolved = detail if isinstance(detail, dict) else {}
    cache[group_id] = resolved
    return resolved


async def decide_row(
    row: StaleCouponRow,
    index: dict[str, dict],
    conflicts: set[str],
    member_api,
    detail_cache: dict[str, dict],
) -> BackfillDecision:
    """判定单条骨架券行能否回填，并给出待写入字段。"""
    if not row.coupon_id:
        return BackfillDecision(row, CATEGORY_AMBIGUOUS, REASON_COUPON_ID_MISSING)
    if not row.mobile:
        return BackfillDecision(row, CATEGORY_AMBIGUOUS, REASON_MOBILE_MISSING)
    if row.coupon_id in conflicts:
        return BackfillDecision(row, CATEGORY_AMBIGUOUS, REASON_DUPLICATE_PAYLOAD)
    coupon = index.get(row.coupon_id)
    if coupon is None:
        return BackfillDecision(row, CATEGORY_EXPIRED, REASON_COUPON_NOT_RETURNED)
    raw_status = str(coupon.get("youzan_coupon_status") or coupon.get("status") or "")
    mapped_status = map_coupon_status(raw_status)
    if not mapped_status:
        # 上游状态无法映射（INVALID / 未知词表）：本地没有对应事实，不写库。
        return BackfillDecision(row, CATEGORY_EXPIRED, REASON_STATUS_NOT_MAPPABLE)
    if mapped_status != row.status:
        # 有赞与本地状态冲突：改了会让券在两个账本里各说各话，保留原行。
        return BackfillDecision(
            row,
            CATEGORY_AMBIGUOUS,
            REASON_STATUS_CONFLICT,
            note=f"local={row.status or '(empty)'} youzan={mapped_status}",
        )
    group_id = row.coupon_group_id or str(coupon.get("coupon_group_id") or "")
    if not group_id:
        return BackfillDecision(row, CATEGORY_MISSING, REASON_TEMPLATE_MISSING)
    detail = await _fetch_template_detail(member_api, group_id, detail_cache)
    if not detail:
        return BackfillDecision(row, CATEGORY_MISSING, REASON_TEMPLATE_MISSING)
    template = parse_youzan_template(detail)
    if not template.id:
        return BackfillDecision(row, CATEGORY_MISSING, REASON_TEMPLATE_MISSING)
    template_fields = extract_template_fields(coupon, detail)
    title = str(coupon.get("title") or coupon.get("coupon_name") or template.name)
    if not title:
        return BackfillDecision(row, CATEGORY_MISSING, REASON_TITLE_MISSING)
    value_fen = template.value_fen or to_fen(
        coupon.get("value") or coupon.get("amount") or coupon.get("coupon_value")
    )
    occurred_at = format_millis_datetime(coupon.get("take_at")) or row.occurred_at
    fields: dict[str, object] = {
        "coupon_group_id": group_id,
        "title": title,
        "value_fen": value_fen,
        "template_id": template.id,
        "valid_from": template_fields["valid_from"],
        "valid_until": template_fields["valid_until"],
        "occurred_at": occurred_at,
        "detail_json": json.dumps(coupon, ensure_ascii=False),
    }
    return BackfillDecision(
        row,
        CATEGORY_BACKFILLED,
        REASON_COUPON_FOUND,
        fields,
        {
            "id": template.id,
            "name": template.name,
            "coupon_type": template.coupon_type,
            "threshold_fen": template.threshold_fen,
            "value_fen": template.value_fen,
            "discount_bp": template.discount_bp,
            "cap_fen": template.cap_fen,
            "valid_from": template.valid_from,
            "valid_until": template.valid_until,
            "scope_json": template.scope_json,
            "status": template.status,
            "source": template.source,
        },
    )


async def plan_backfill(
    rows: list[StaleCouponRow], member_api
) -> list[BackfillDecision]:
    """按手机号去重向有赞核对，给出每条骨架券行的判定结论。"""
    decisions: list[BackfillDecision] = []
    detail_cache: dict[str, dict] = {}
    rows_by_mobile: dict[str, list[StaleCouponRow]] = {}
    for row in rows:
        rows_by_mobile.setdefault(row.mobile, []).append(row)
    for mobile, mobile_rows in rows_by_mobile.items():
        coupons, error = await _fetch_coupons(member_api, mobile)
        index, conflicts = _index_coupons(coupons)
        for row in mobile_rows:
            if error:
                decisions.append(
                    BackfillDecision(
                        row, CATEGORY_AMBIGUOUS, REASON_YOUZAN_QUERY_FAILED, note=error
                    )
                )
                continue
            decisions.append(
                await decide_row(row, index, conflicts, member_api, detail_cache)
            )
    return decisions


def apply_backfill(
    connection: sqlite3.Connection,
    decisions: list[BackfillDecision],
    *,
    upsert_templates: bool,
) -> ApplyOutcome:
    """在单个事务内回填骨架券行；任一行失败整体回滚。"""
    outcome = ApplyOutcome()
    backfilled = [item for item in decisions if item.category == CATEGORY_BACKFILLED]
    if not backfilled:
        return outcome
    templates: dict[str, dict[str, object]] = {}
    for item in backfilled:
        template = item.template
        if template:
            templates[str(template["id"])] = template
    finished_at = format_beijing(datetime.now(BEIJING_TZ))
    connection.execute("BEGIN IMMEDIATE")
    try:
        for item in backfilled:
            fields = item.fields
            row = item.row
            cursor = connection.execute(
                BACKFILL_SQL,
                (
                    fields["coupon_group_id"],
                    fields["title"],
                    fields["value_fen"],
                    fields["template_id"],
                    fields["valid_from"],
                    fields["valid_until"],
                    fields["occurred_at"],
                    fields["detail_json"],
                    row.row_id,
                    row.coupon_id,
                    row.mobile,
                    STALE_TITLE,
                    STALE_VALUE_FEN,
                    STALE_TEMPLATE_ID,
                ),
            )
            if int(cursor.rowcount or 0) != 1:
                raise BackfillFailed(
                    f"骨架券行 {row.row_id} 更新命中数异常，事务整体回滚"
                )
            outcome.updated_ids.append(row.row_id)
        if upsert_templates:
            for template_id in sorted(templates):
                template = templates[template_id]
                connection.execute(
                    TEMPLATE_UPSERT_SQL,
                    (
                        template["id"],
                        template["name"],
                        template["coupon_type"],
                        template["threshold_fen"],
                        template["value_fen"],
                        template["discount_bp"],
                        template["cap_fen"],
                        template["valid_from"],
                        template["valid_until"],
                        template["scope_json"],
                        template["status"],
                        template["source"],
                        finished_at,
                        finished_at,
                    ),
                )
                outcome.templates_upserted.append(template_id)
        connection.execute("COMMIT")
        outcome.committed = True
    except BackfillFailed as exc:
        connection.execute("ROLLBACK")
        outcome.updated_ids = []
        outcome.templates_upserted = []
        outcome.failures.append({"reason": str(exc)})
        outcome.error = str(exc)
        logger.error("回填失败已整体回滚: %s", exc)
    except sqlite3.Error as exc:
        connection.execute("ROLLBACK")
        outcome.updated_ids = []
        outcome.templates_upserted = []
        outcome.failures.append({"reason": f"update_error: {exc}"})
        outcome.error = f"写库失败已回滚: {exc}"
        logger.error("写库失败已整体回滚: %s", exc)
    return outcome


def format_beijing(moment: datetime) -> str:
    """把时间格式化成库内统一的字符串格式。"""
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _as_int(value: object) -> int:
    """容忍转换整数，失败返回 0。"""
    if value is None:
        return 0
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def _count_by(decisions: list[BackfillDecision], key: str) -> dict[str, int]:
    """按分类或原因分组计数，结果按键排序。"""
    counts: dict[str, int] = {}
    for item in decisions:
        value = getattr(item, key) or ""
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _count_rows_by(rows: list[StaleCouponRow], key: str) -> dict[str, int]:
    """按骨架券行的字段分组计数，结果按键排序。"""
    counts: dict[str, int] = {}
    for row in rows:
        value = str(getattr(row, key) or "") or "(empty)"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _decision_row(decision: BackfillDecision) -> dict[str, object]:
    """把单条判定结论转成脱敏后的报告条目。"""
    row = decision.row
    fields = decision.fields
    return {
        "id": row.row_id,
        "coupon_id": row.coupon_id,
        "mobile": mask_sensitive(row.mobile),
        "local_status": row.status or "(empty)",
        "coupon_group_id": row.coupon_group_id or "(empty)",
        "category": decision.category,
        "reason": decision.reason,
        "reason_text": REASON_TEXT.get(decision.reason, ""),
        "note": decision.note,
        "new_title": str(fields.get("title", "")) if fields else "",
        "new_value_fen": _as_int(fields.get("value_fen")) if fields else 0,
        "new_template_id": str(fields.get("template_id", "")) if fields else "",
        "new_valid_from": str(fields.get("valid_from", "")) if fields else "",
        "new_valid_until": str(fields.get("valid_until", "")) if fields else "",
        "new_occurred_at": str(fields.get("occurred_at", "")) if fields else "",
    }


def build_report(
    rows: list[StaleCouponRow],
    decisions: list[BackfillDecision],
    outcome: ApplyOutcome,
    *,
    mode: str,
    db_path: str,
    guard: dict[str, object],
    upsert_templates: bool,
) -> dict[str, object]:
    """生成稳定结构的回填报告。"""
    by_category = _count_by(decisions, "category")
    by_reason = _count_by(decisions, "reason")
    kept = len(decisions) - by_category.get(CATEGORY_BACKFILLED, 0)
    status_by_category: dict[str, int] = {}
    for item in decisions:
        label = f"{item.category}:{item.row.status or '(empty)'}"
        status_by_category[label] = status_by_category.get(label, 0) + 1
    template_ids = sorted(
        {
            str(item.fields.get("template_id", ""))
            for item in decisions
            if item.category == CATEGORY_BACKFILLED and item.fields
        }
    )
    return {
        "status": "failed" if outcome.error else "ok",
        "mode": mode,
        "db": db_path,
        "run_at": format_beijing(datetime.now(BEIJING_TZ)),
        "production_guard": guard,
        "options": {"upsert_templates": upsert_templates},
        "scope": {
            "stale_total": len(rows),
            "distinct_mobiles": len({row.mobile for row in rows}),
            "by_status": _count_rows_by(rows, "status"),
            "by_source": _count_rows_by(rows, "source"),
            "by_coupon_group_id": _count_rows_by(rows, "coupon_group_id"),
        },
        "stats": {
            "by_category": by_category,
            "by_reason": by_reason,
            "by_category_and_local_status": dict(sorted(status_by_category.items())),
        },
        "plan": {
            "would_backfill": by_category.get(CATEGORY_BACKFILLED, 0),
            "would_keep": kept,
            "template_ids": template_ids,
        },
        "result": {
            "updated": len(outcome.updated_ids),
            "updated_ids": outcome.updated_ids,
            "templates_upserted": outcome.templates_upserted,
            "failures": outcome.failures,
            "committed": outcome.committed,
            "error": outcome.error,
        },
        "rows": [_decision_row(item) for item in decisions],
        "summary": {
            "stale_total": len(rows),
            "backfilled": by_category.get(CATEGORY_BACKFILLED, 0),
            "expired": by_category.get(CATEGORY_EXPIRED, 0),
            "missing": by_category.get(CATEGORY_MISSING, 0),
            "ambiguous": by_category.get(CATEGORY_AMBIGUOUS, 0),
            "updated": len(outcome.updated_ids),
            "committed": outcome.committed,
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数；默认 dry-run，不写库。"""
    parser = argparse.ArgumentParser(
        description="用有赞当前券数据定向回填 coupon_inventory 的骨架券行"
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
    parser.add_argument(
        "--upsert-templates",
        action="store_true",
        help=(
            "把本次回填引用到的有赞券模板同步进 coupon_templates（幂等）；"
            "不加该参数时只回填 coupon_inventory。"
        ),
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


async def run_backfill(
    db_path: Path,
    member_api,
    *,
    should_apply: bool,
    upsert_templates: bool,
) -> tuple[list[StaleCouponRow], list[BackfillDecision], ApplyOutcome]:
    """在目标库上完成核对（可选回填）并返回判定结论。"""
    with closing(_connect(db_path, read_only=not should_apply)) as connection:
        if not _table_exists(connection, "coupon_inventory"):
            raise sqlite3.OperationalError("目标库缺少 coupon_inventory 表")
        if not _column_exists(connection, "coupon_inventory", "template_id"):
            raise sqlite3.OperationalError(
                "目标库 coupon_inventory 缺少 template_id 列"
            )
        rows = fetch_stale_rows(connection)
        decisions = await plan_backfill(rows, member_api)
        outcome = ApplyOutcome()
        if should_apply:
            outcome = apply_backfill(
                connection, decisions, upsert_templates=upsert_templates
            )
        return rows, decisions, outcome


def _build_member_api():
    """构造真实的有赞会员账务域客户端，返回 (成员 API, 底层云客户端)。"""
    from app.service.youzan.client import YouzanClient
    from app.service.youzan.member_api import YouzanMemberApi

    client = YouzanClient()
    return YouzanMemberApi(client), client


async def async_main(argv: list[str] | None = None, member_api=None) -> int:
    """脚本主流程：核对（可选回填）并输出报告。

    `member_api` 只在测试里注入假的有赞客户端；缺省时构造真实客户端。
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
        if member_api is None:
            member_api, client = _build_member_api()
        rows, decisions, outcome = await run_backfill(
            db_path,
            member_api,
            should_apply=bool(args.apply),
            upsert_templates=bool(args.upsert_templates),
        )
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
            upsert_templates=bool(args.upsert_templates),
        )
    )
    emit_report(report, args.output)
    summary = report.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    logger.info(
        "回填核对完成 mode=%s stale=%s would_backfill=%s updated=%s committed=%s",
        report["mode"],
        summary.get("stale_total", 0),
        summary.get("backfilled", 0),
        summary.get("updated", 0),
        summary.get("committed", False),
    )
    if outcome.error:
        logger.error("回填未完成: %s", outcome.error)
        return EXIT_FAILED
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """脚本入口，返回进程退出码。"""
    _configure_logging()
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
