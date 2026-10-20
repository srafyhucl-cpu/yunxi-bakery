"""处置有赞 webhook 死信队列与历史审计失败记录。

背景
----
`inbox_events` 中 `queue_name='youzan_webhook'` 的死信任务在 2026-08 期间
因两个已修复的缺陷堆积：

- `event_handler` 拿不到请求级数据库连接，报
  ``'NoneType' object has no attribute 'in_transaction'``；
- `member_balance_repo.mirror_youzan_points` 用空手机号重复建档，报
  ``UNIQUE constraint failed: member_balance.mobile``。

两个缺陷均已在当前代码修复，死信任务可以安全回到队列重放。本脚本只做
「把死信退回队列」这一件事，不重放任何业务逻辑，也不改动
`message_key` / `payload_json` / `created_at`。

`youzan_webhook_events` 中 `status='failed'` 的历史审计失败属于旧版 item
事件解析缺陷（msg_id 被当整数解析、知识库对象为空、向量索引越界、数据库
锁冲突），重放没有业务意义，改为显式标记 `skipped` 并保留原始错误信息，
不删除任何记录。

安全约束
--------
- 必须显式传 ``--db``，脚本不猜测任何默认库路径；
- 默认 dry-run，只有 ``--apply`` 才写库；
- 路径疑似生产部署目录时必须额外传 ``--allow-production``；
- 任何写操作在单个事务内完成，任一行失败整体回滚并逐条报错。

用法
----
    # 默认 dry-run：只出报告，不写库
    python scripts/resolve_youzan_dead_letters.py --db /path/to/bot.db

    # 真正回放死信
    python scripts/resolve_youzan_dead_letters.py --db /path/to/bot.db --apply

    # 同时把历史审计失败标记为 skipped
    python scripts/resolve_youzan_dead_letters.py --db /path/to/bot.db \
        --resolve-audit-failed --apply

    # 指向生产路径时必须显式声明
    python scripts/resolve_youzan_dead_letters.py \
        --db /opt/apps/yunxi-bakery/backend/data/bot.db --apply --allow-production
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
import urllib.parse
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

QUEUE_NAME = "youzan_webhook"
DEAD_LETTER_STATUS = "dead_letter"
REPLAY_TARGET_STATUS = "received"
AUDIT_FAILED_STATUS = "failed"
AUDIT_RESOLVED_STATUS = "skipped"
AUDIT_HISTORICAL_ERROR_TYPE = "historical_invalid_payload"
AUDIT_ERROR_MESSAGE_PREFIX = "[historical_invalid_payload] "
DEFAULT_AUDIT_BUSINESS_TYPE = "item"
DEFAULT_AUDIT_MAX_AGE_DAYS = 30
BUSINESS_TIMEOUT_MS = 15000
BEIJING_TZ = timezone(timedelta(hours=8))

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REJECTED = 2

# 日志统一走 stderr，保证 stdout 只有一份可被机器解析的 JSON 报告。
logger = logging.getLogger("yunxi_bot.resolve_youzan_dead_letters")
logger.propagate = False

_MOBILE_PATTERN = re.compile(r"(?<!\d)1\d{10}(?!\d)")
_PRODUCTION_PATH_SEGMENTS = frozenset(
    {"yunxibakebot", "yunxi-bakery", "prod", "production"}
)

# next_attempt_at 在 v018 建表时是 NOT NULL，写 NULL 会触发约束失败；
# 该列对 status='received' 的认领查询无意义，NOT NULL 时用
# datetime('now') 表达「立即可被认领」的等价语义。
REPLAY_SQL_NULLABLE = (
    "UPDATE inbox_events SET status = ?, attempt_count = 0, lease_until = NULL, "
    "next_attempt_at = NULL, last_error = '', updated_at = datetime('now') "
    "WHERE id = ? AND status = ?"
)
REPLAY_SQL_NOT_NULL = (
    "UPDATE inbox_events SET status = ?, attempt_count = 0, lease_until = NULL, "
    "next_attempt_at = datetime('now'), last_error = '', updated_at = datetime('now') "
    "WHERE id = ? AND status = ?"
)
AUDIT_RESOLVE_SQL = (
    "UPDATE youzan_webhook_events SET status = ?, error_type = ?, error_message = ?, "
    "updated_at = datetime('now') WHERE id = ? AND status = ?"
)


class TargetRejected(Exception):
    """目标库路径不满足安全前提。"""


@dataclass(frozen=True)
class DeadLetterRow:
    """一条死信 inbox 记录。"""

    row_id: int
    message_key: str
    payload_json: str
    attempt_count: int
    last_error: str
    created_at: str


@dataclass(frozen=True)
class AuditFailedRow:
    """一条失败的有赞 webhook 审计记录。"""

    row_id: int
    msg_id: str
    event_type: str
    business_type: str
    business_key: str
    error_type: str
    error_message: str
    received_at: str


@dataclass
class InboxPlan:
    """死信回放计划。"""

    total: int = 0
    eligible: list[DeadLetterRow] = field(default_factory=list)
    skipped: list[dict[str, object]] = field(default_factory=list)
    out_of_scope: list[dict[str, object]] = field(default_factory=list)
    event_type_by_id: dict[int, str] = field(default_factory=dict)
    by_event_type: dict[str, int] = field(default_factory=dict)
    by_last_error: dict[str, int] = field(default_factory=dict)
    by_created_day: dict[str, int] = field(default_factory=dict)


@dataclass
class PointsImpact:
    """POINTS 事件回放对会员积分余额的预估影响（只读分析）。"""

    available: bool = False
    checked: int = 0
    backward: int = 0
    backward_delta: int = 0
    forward: int = 0
    equal: int = 0
    no_account: int = 0
    empty_mobile: int = 0
    samples: list[dict[str, object]] = field(default_factory=list)


@dataclass
class AuditPlan:
    """历史审计失败处置计划。"""

    total: int = 0
    rows: list[AuditFailedRow] = field(default_factory=list)
    resolvable: list[AuditFailedRow] = field(default_factory=list)
    guard_reasons: dict[int, str] = field(default_factory=dict)
    by_error_type: dict[str, int] = field(default_factory=dict)


@dataclass
class ApplyOutcome:
    """一次写库执行的结果。"""

    replayed: set[int] = field(default_factory=set)
    resolved: set[int] = field(default_factory=set)
    inbox_failures: list[dict[str, object]] = field(default_factory=list)
    audit_failures: list[dict[str, object]] = field(default_factory=list)
    committed: bool = False
    error: str = ""

    @property
    def failures(self) -> list[dict[str, object]]:
        """全部失败明细。"""
        return [*self.inbox_failures, *self.audit_failures]


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


def mask_sensitive(text: str) -> str:
    """把中国大陆手机号脱敏，只保留前 3 位与后 4 位。"""
    if not text:
        return text
    return _MOBILE_PATTERN.sub(
        lambda match: f"{match.group(0)[:3]}****{match.group(0)[-4:]}", text
    )


def looks_like_production_path(raw_path: str) -> bool:
    """判断路径是否疑似生产部署目录。"""
    normalized = raw_path.replace("\\", "/").strip().lower()
    segments = [segment for segment in normalized.split("/") if segment]
    if "opt" in segments and "apps" in segments:
        # 生产部署根目录 /opt/apps/<应用名>
        return True
    return any(segment in _PRODUCTION_PATH_SEGMENTS for segment in segments)


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


def classify_payload(payload_json: str) -> tuple[str, str]:
    """判定死信载荷是否可回放，返回 (事件类型, 不可回放原因)。

    原因为空串表示载荷可回放；事件类型即使不可回放也会尽量解析出来，
    便于按类型统计。
    """
    try:
        payload = json.loads(payload_json)
    except (TypeError, ValueError) as exc:
        return "", f"invalid_json: {exc}"
    if not isinstance(payload, dict):
        return "", f"payload_not_object: {type(payload).__name__}"
    event_type = str(payload.get("event_type") or payload.get("type") or "").strip()
    if not event_type:
        return "", "missing_event_type"
    if isinstance(payload.get("body"), dict):
        return event_type, ""
    if "body" not in payload and "msg" in payload:
        # 原始推送体直接放在载荷顶层时，载荷本身即业务体
        return event_type, ""
    return event_type, "missing_body"


def _parse_timestamp(value: str) -> datetime | None:
    """解析库内时间字符串（北京时间，无时区）。"""
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BEIJING_TZ)
    except (TypeError, ValueError):
        return None


def fetch_dead_letters(connection: sqlite3.Connection) -> list[DeadLetterRow]:
    """读取指定队列的死信任务。"""
    rows = connection.execute(
        "SELECT id, message_key, payload_json, attempt_count, last_error, created_at "
        "FROM inbox_events "
        "WHERE queue_name = ? AND status = ? "
        "ORDER BY id",
        (QUEUE_NAME, DEAD_LETTER_STATUS),
    ).fetchall()
    return [
        DeadLetterRow(
            row_id=int(row[0]),
            message_key=str(row[1]),
            payload_json=str(row[2]),
            attempt_count=int(row[3]),
            last_error=str(row[4]),
            created_at=str(row[5]),
        )
        for row in rows
    ]


def fetch_audit_failed(connection: sqlite3.Connection) -> list[AuditFailedRow]:
    """读取状态为 failed 的有赞 webhook 审计记录。"""
    rows = connection.execute(
        "SELECT id, msg_id, event_type, business_type, business_key, "
        "error_type, error_message, received_at "
        "FROM youzan_webhook_events WHERE status = ? ORDER BY id",
        (AUDIT_FAILED_STATUS,),
    ).fetchall()
    return [
        AuditFailedRow(
            row_id=int(row[0]),
            msg_id=str(row[1]),
            event_type=str(row[2]),
            business_type=str(row[3]),
            business_key=str(row[4]),
            error_type=str(row[5]),
            error_message=str(row[6]),
            received_at=str(row[7]),
        )
        for row in rows
    ]


def build_inbox_plan(
    rows: list[DeadLetterRow], *, allowed_event_types: set[str] | None = None
) -> InboxPlan:
    """把死信分成可回放、不可回放与不在本次范围内三桶，并统计分布。

    `allowed_event_types` 为空表示不按事件类型筛选；给出后只回放列出的类型，
    其余进入 out_of_scope 桶（不算载荷非法，只是本次不处理）。
    """
    plan = InboxPlan(total=len(rows))
    for row in rows:
        event_type, reason = classify_payload(row.payload_json)
        type_key = event_type or "unknown"
        plan.event_type_by_id[row.row_id] = type_key
        plan.by_event_type[type_key] = plan.by_event_type.get(type_key, 0) + 1
        error_key = mask_sensitive(row.last_error) or "unknown"
        plan.by_last_error[error_key] = plan.by_last_error.get(error_key, 0) + 1
        day = row.created_at[:10] or "unknown"
        plan.by_created_day[day] = plan.by_created_day.get(day, 0) + 1
        if reason:
            plan.skipped.append(
                {
                    "id": row.row_id,
                    "message_key": mask_sensitive(row.message_key),
                    "event_type": type_key,
                    "reason": reason,
                }
            )
            continue
        if allowed_event_types and event_type not in allowed_event_types:
            plan.out_of_scope.append(
                {
                    "id": row.row_id,
                    "message_key": mask_sensitive(row.message_key),
                    "event_type": type_key,
                    "reason": "event_type_not_in_scope",
                }
            )
            continue
        plan.eligible.append(row)
    plan.by_event_type = dict(sorted(plan.by_event_type.items()))
    plan.by_last_error = dict(sorted(plan.by_last_error.items()))
    plan.by_created_day = dict(sorted(plan.by_created_day.items()))
    return plan


def extract_points_total(payload_json: str) -> tuple[str, int | None]:
    """提取 POINTS 载荷里的手机号与外部权威积分总额。

    有赞把业务体放在 `body.msg`（URL 编码的 JSON 字符串）里，解析口径与
    `app/service/youzan/event_handler.py` 保持一致。
    """
    try:
        payload = json.loads(payload_json)
    except (TypeError, ValueError):
        return "", None
    if not isinstance(payload, dict):
        return "", None
    body = payload.get("body")
    if not isinstance(body, dict):
        return "", None
    raw_msg = body.get("msg")
    if isinstance(raw_msg, dict):
        msg = raw_msg
    else:
        try:
            msg = json.loads(urllib.parse.unquote(str(raw_msg or "")))
        except (TypeError, ValueError):
            return "", None
    if not isinstance(msg, dict):
        return "", None
    mobile = str(msg.get("mobile") or "")
    try:
        return mobile, int(msg.get("total"))
    except (TypeError, ValueError):
        return mobile, None


def build_points_impact(
    connection: sqlite3.Connection, plan: InboxPlan
) -> PointsImpact:
    """预估 POINTS 死信回放会把会员积分余额挪动多少（只读）。

    锚点口径下 `mirror_youzan_points` 会把余额重置为事件里的外部权威总额。
    死信是 2026-08 的旧事件，若会员此后已有新的 POINTS 事件被正常处理，
    重放旧事件会把余额**改小**。这里逐条比对事件总额与当前锚点，
    让操作者在 apply 之前先看清影响面。
    """
    impact = PointsImpact()
    if not _table_exists(connection, "member_balance"):
        return impact
    if not _column_exists(connection, "member_balance", "youzan_points_base"):
        # 锚点列是 v038 才加的；老库没有锚点口径，无法预估影响。
        return impact
    impact.available = True
    for row in plan.eligible:
        if plan.event_type_by_id.get(row.row_id) != "POINTS":
            continue
        mobile, event_total = extract_points_total(row.payload_json)
        if event_total is None:
            continue
        impact.checked += 1
        if not mobile:
            # 空手机号会被 mirror_youzan_points 跳过（已修复的缺陷），
            # 只写积分流水，不动余额。
            impact.empty_mobile += 1
            continue
        account = connection.execute(
            "SELECT points, youzan_points_base FROM member_balance WHERE mobile = ? "
            "LIMIT 1",
            (mobile,),
        ).fetchone()
        if account is None:
            impact.no_account += 1
            continue
        base = int(account[1] or 0)
        delta = event_total - base
        if delta < 0:
            impact.backward += 1
            impact.backward_delta += -delta
        elif delta > 0:
            impact.forward += 1
        else:
            impact.equal += 1
        if len(impact.samples) < 20 and delta != 0:
            impact.samples.append(
                {
                    "id": row.row_id,
                    "mobile": mask_sensitive(mobile),
                    "event_total": event_total,
                    "current_youzan_points_base": base,
                    "delta": delta,
                }
            )
    return impact


def build_audit_plan(
    rows: list[AuditFailedRow],
    *,
    business_type: str,
    max_age_days: int,
    now: datetime,
) -> AuditPlan:
    """筛出可以按「历史无效载荷」处置的失败审计记录。"""
    plan = AuditPlan(total=len(rows), rows=list(rows))
    cutoff = now - timedelta(days=max_age_days)
    for row in rows:
        error_key = row.error_type or "unknown"
        plan.by_error_type[error_key] = plan.by_error_type.get(error_key, 0) + 1
        if row.business_type != business_type:
            plan.guard_reasons[row.row_id] = "business_type_not_in_scope"
            continue
        received_at = _parse_timestamp(row.received_at)
        if received_at is None:
            plan.guard_reasons[row.row_id] = "unparsable_received_at"
            continue
        if received_at >= cutoff:
            plan.guard_reasons[row.row_id] = "not_historical"
            continue
        plan.resolvable.append(row)
    plan.by_error_type = dict(sorted(plan.by_error_type.items()))
    return plan


def next_attempt_reset_mode(connection: sqlite3.Connection) -> str:
    """判断 next_attempt_at 是否允许写 NULL，返回实际采用的复位方式。"""
    for row in connection.execute("PRAGMA table_info(inbox_events)"):
        if str(row[1]) == "next_attempt_at":
            return "null" if int(row[3]) == 0 else "datetime('now')"
    return "datetime('now')"


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
    for row in connection.execute(f"PRAGMA table_info({table_name})"):
        if str(row[1]) == column_name:
            return True
    return False


def _connect(db_path: Path, *, read_only: bool) -> sqlite3.Connection:
    """打开目标库；dry-run 一律只读打开，避免任何意外写入。"""
    if read_only:
        connection = sqlite3.connect(
            f"{db_path.resolve().as_uri()}?mode=ro",
            uri=True,
            timeout=BUSINESS_TIMEOUT_MS,
            isolation_level=None,
        )
    else:
        connection = sqlite3.connect(
            str(db_path), timeout=BUSINESS_TIMEOUT_MS, isolation_level=None
        )
    connection.execute(f"PRAGMA busy_timeout = {BUSINESS_TIMEOUT_MS}")
    return connection


def _replay_inbox(
    connection: sqlite3.Connection, plan: InboxPlan, reset_mode: str
) -> tuple[set[int], list[dict[str, object]]]:
    """在当前事务内回放死信，返回 (成功行 id 集合, 失败明细)。"""
    sql = REPLAY_SQL_NULLABLE if reset_mode == "null" else REPLAY_SQL_NOT_NULL
    replayed: set[int] = set()
    failures: list[dict[str, object]] = []
    for row in plan.eligible:
        try:
            cursor = connection.execute(
                sql,
                (REPLAY_TARGET_STATUS, row.row_id, DEAD_LETTER_STATUS),
            )
        except sqlite3.Error as exc:
            logger.error("回放死信失败 id=%s err=%s", row.row_id, exc)
            failures.append(
                {
                    "id": row.row_id,
                    "message_key": mask_sensitive(row.message_key),
                    "reason": f"update_error: {exc}",
                }
            )
            continue
        if int(cursor.rowcount or 0) != 1:
            failures.append(
                {
                    "id": row.row_id,
                    "message_key": mask_sensitive(row.message_key),
                    "reason": "status_changed_concurrently",
                }
            )
            continue
        replayed.add(row.row_id)
    return replayed, failures


def _resolve_audit(
    connection: sqlite3.Connection, plan: AuditPlan
) -> tuple[set[int], list[dict[str, object]]]:
    """在当前事务内把历史失败审计标记为 skipped，返回 (成功行 id 集合, 失败明细)。"""
    resolved: set[int] = set()
    failures: list[dict[str, object]] = []
    for row in plan.resolvable:
        error_message = f"{AUDIT_ERROR_MESSAGE_PREFIX}{row.error_message}"
        try:
            cursor = connection.execute(
                AUDIT_RESOLVE_SQL,
                (
                    AUDIT_RESOLVED_STATUS,
                    AUDIT_HISTORICAL_ERROR_TYPE,
                    error_message,
                    row.row_id,
                    AUDIT_FAILED_STATUS,
                ),
            )
        except sqlite3.Error as exc:
            logger.error("标记历史审计失败失败 id=%s err=%s", row.row_id, exc)
            failures.append(
                {
                    "id": row.row_id,
                    "msg_id": mask_sensitive(row.msg_id),
                    "reason": f"update_error: {exc}",
                }
            )
            continue
        if int(cursor.rowcount or 0) != 1:
            failures.append(
                {
                    "id": row.row_id,
                    "msg_id": mask_sensitive(row.msg_id),
                    "reason": "status_changed_concurrently",
                }
            )
            continue
        resolved.add(row.row_id)
    return resolved, failures


def _audit_items(
    plan: AuditPlan, *, resolve_requested: bool, resolved_ids: set[int]
) -> list[dict[str, object]]:
    """输出审计失败明细，逐条给出处置动作。"""
    items: list[dict[str, object]] = []
    for row in plan.rows:
        if row.row_id in resolved_ids:
            action = "resolved"
        elif row.row_id in plan.guard_reasons:
            action = "skipped_by_guard"
        elif resolve_requested:
            action = "would_resolve"
        else:
            action = "report_only"
        item: dict[str, object] = {
            "id": row.row_id,
            "msg_id": mask_sensitive(row.msg_id),
            "event_type": row.event_type,
            "business_type": row.business_type,
            "business_key": mask_sensitive(row.business_key),
            "error_type": row.error_type,
            "error_message": mask_sensitive(row.error_message),
            "received_at": row.received_at,
            "action": action,
        }
        if row.row_id in plan.guard_reasons:
            item["reason"] = plan.guard_reasons[row.row_id]
        items.append(item)
    return items


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数；默认 dry-run，不写库。"""
    parser = argparse.ArgumentParser(
        description="处置有赞 webhook 死信队列与历史审计失败记录"
    )
    parser.add_argument("--db", required=True, help="目标 SQLite 数据库路径（必填）")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写库；不加该参数时只做 dry-run。",
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="允许对疑似生产路径的数据库执行操作。",
    )
    parser.add_argument(
        "--resolve-audit-failed",
        action="store_true",
        help="同时把历史 failed 审计记录标记为 skipped（需配合 --apply 才写库）。",
    )
    parser.add_argument(
        "--skip-inbox",
        action="store_true",
        help="只处理审计失败、不回放 inbox 死信；避免审计清理误触发会员事件回放。",
    )
    parser.add_argument(
        "--event-type",
        action="append",
        default=[],
        help="只回放指定事件类型的死信，可重复传入；缺省回放全部类型。",
    )
    parser.add_argument(
        "--audit-failed-business-type",
        default=DEFAULT_AUDIT_BUSINESS_TYPE,
        help="允许处置的历史审计失败业务类型，默认 item。",
    )
    parser.add_argument(
        "--audit-failed-max-age-days",
        type=int,
        default=DEFAULT_AUDIT_MAX_AGE_DAYS,
        help="历史审计失败的最大天数阈值，默认 30 天。",
    )
    parser.add_argument("--output", default="", help="把 JSON 报告额外写入指定文件")
    return parser.parse_args(argv)


def _inbox_report(
    plan: InboxPlan,
    reset_mode: str,
    replayed: set[int],
    failures: list[dict[str, object]],
    *,
    skipped_by_flag: bool = False,
) -> dict[str, object]:
    """生成 inbox 部分的稳定报告结构。"""
    return {
        "queue_name": QUEUE_NAME,
        "target_status": DEAD_LETTER_STATUS,
        "replay_target_status": REPLAY_TARGET_STATUS,
        "dead_letter_total": plan.total,
        "eligible": len(plan.eligible),
        "skipped_invalid": len(plan.skipped),
        "out_of_scope": len(plan.out_of_scope),
        "replayed": len(replayed),
        "would_replay": len(plan.eligible),
        "skipped_by_inbox_flag": skipped_by_flag,
        "next_attempt_at_reset": reset_mode,
        "by_event_type": plan.by_event_type,
        "by_last_error": plan.by_last_error,
        "by_created_day": plan.by_created_day,
        "skipped": plan.skipped,
        "out_of_scope_rows": plan.out_of_scope,
        "failed": failures,
    }


def _impact_report(impact: PointsImpact) -> dict[str, object]:
    """生成 POINTS 余额影响预估的稳定报告结构。"""
    return {
        "available": impact.available,
        "note": (
            "mirror_youzan_points 会把余额重置为事件内的外部权威总额；"
            "backward 表示重放会把会员积分余额改小"
        ),
        "checked_points_events": impact.checked,
        "backward": impact.backward,
        "backward_points_total": impact.backward_delta,
        "forward": impact.forward,
        "equal": impact.equal,
        "no_account": impact.no_account,
        "empty_mobile": impact.empty_mobile,
        "samples": impact.samples,
    }


def _audit_report(
    plan: AuditPlan,
    resolve_requested: bool,
    resolved: set[int],
    failures: list[dict[str, object]],
) -> dict[str, object]:
    """生成 audit_failed 部分的稳定报告结构。"""
    return {
        "target_status": AUDIT_FAILED_STATUS,
        "resolve_status": AUDIT_RESOLVED_STATUS,
        "error_type": AUDIT_HISTORICAL_ERROR_TYPE,
        "resolve_requested": resolve_requested,
        "total": plan.total,
        "eligible": len(plan.resolvable),
        "skipped_by_guard": len(plan.guard_reasons),
        "resolved": len(resolved),
        "would_resolve": len(plan.resolvable) if resolve_requested else 0,
        "by_error_type": plan.by_error_type,
        "items": _audit_items(
            plan, resolve_requested=resolve_requested, resolved_ids=resolved
        ),
        "failed": failures,
    }


def _summary(
    inbox_plan: InboxPlan,
    audit_plan: AuditPlan,
    replayed: set[int],
    resolved: set[int],
    failures: list[dict[str, object]],
    committed: bool,
) -> dict[str, object]:
    """生成概要字段。"""
    return {
        "dead_letter_total": inbox_plan.total,
        "eligible": len(inbox_plan.eligible),
        "skipped_invalid": len(inbox_plan.skipped),
        "out_of_scope": len(inbox_plan.out_of_scope),
        "replayed": len(replayed),
        "audit_failed_total": audit_plan.total,
        "audit_eligible": len(audit_plan.resolvable),
        "audit_resolved": len(resolved),
        "failed_rows": len(failures),
        "committed": committed,
    }


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


def main(argv: list[str] | None = None) -> int:
    """脚本入口，返回进程退出码。"""
    _configure_logging()
    args = parse_args(argv)
    if args.skip_inbox and not args.resolve_audit_failed:
        logger.error("--skip-inbox 只能与 --resolve-audit-failed 一起使用")
        return EXIT_REJECTED
    report: dict[str, object] = {
        "status": "ok",
        "mode": "apply" if args.apply else "dry-run",
        "db": str(args.db),
        "inbox": {},
        "points_impact": {},
        "audit_failed": {},
        "summary": {},
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
    try:
        with closing(_connect(db_path, read_only=not args.apply)) as connection:
            return _run_on_database(connection, args, report)
    except sqlite3.Error as exc:
        logger.error("数据库操作失败: %s", exc)
        report["status"] = "failed"
        report["error"] = f"数据库操作失败: {exc}"
        emit_report(report, args.output)
        return EXIT_FAILED


def _run_on_database(
    connection: sqlite3.Connection,
    args: argparse.Namespace,
    report: dict[str, object],
) -> int:
    """在目标库上完成计划、处置与报告输出。"""
    missing_tables = [
        name
        for name in ("inbox_events", "youzan_webhook_events")
        if not _table_exists(connection, name)
    ]
    if missing_tables:
        report["status"] = "failed"
        report["error"] = f"目标库缺少必要的表: {', '.join(missing_tables)}"
        report["summary"] = {"missing_tables": missing_tables}
        emit_report(report, args.output)
        logger.error("目标库缺少必要的表: %s", ", ".join(missing_tables))
        return EXIT_FAILED

    inbox_plan = build_inbox_plan(
        fetch_dead_letters(connection),
        allowed_event_types=set(str(item) for item in args.event_type) or None,
    )
    audit_plan = build_audit_plan(
        fetch_audit_failed(connection),
        business_type=str(args.audit_failed_business_type),
        max_age_days=int(args.audit_failed_max_age_days),
        now=datetime.now(BEIJING_TZ),
    )
    reset_mode = next_attempt_reset_mode(connection)
    impact = build_points_impact(connection, inbox_plan)

    outcome = ApplyOutcome()
    if args.apply:
        outcome = _execute_changes(connection, args, inbox_plan, audit_plan, reset_mode)

    report["status"] = "failed" if outcome.failures or outcome.error else "ok"
    report["inbox"] = _inbox_report(
        inbox_plan,
        reset_mode,
        outcome.replayed,
        outcome.inbox_failures,
        skipped_by_flag=bool(args.skip_inbox),
    )
    report["points_impact"] = _impact_report(impact)
    report["audit_failed"] = _audit_report(
        audit_plan,
        bool(args.resolve_audit_failed),
        outcome.resolved,
        outcome.audit_failures,
    )
    report["summary"] = _summary(
        inbox_plan,
        audit_plan,
        outcome.replayed,
        outcome.resolved,
        outcome.failures,
        outcome.committed,
    )
    if outcome.error:
        report["error"] = outcome.error
    elif outcome.failures:
        report["error"] = "存在更新失败行，本次变更已整体回滚"
    emit_report(report, args.output)
    for failure in outcome.failures:
        logger.error(
            "更新失败 id=%s reason=%s", failure.get("id"), failure.get("reason")
        )
    logger.info(
        "处置完成 mode=%s dead_letter=%s eligible=%s replayed=%s "
        "audit_failed=%s resolved=%s failed=%s",
        report["mode"],
        inbox_plan.total,
        len(inbox_plan.eligible),
        len(outcome.replayed),
        audit_plan.total,
        len(outcome.resolved),
        len(outcome.failures),
    )
    return EXIT_FAILED if outcome.failures or outcome.error else EXIT_OK


def _execute_changes(
    connection: sqlite3.Connection,
    args: argparse.Namespace,
    inbox_plan: InboxPlan,
    audit_plan: AuditPlan,
    reset_mode: str,
) -> ApplyOutcome:
    """在单个事务内完成回放与审计处置，任一行失败整体回滚。"""
    outcome = ApplyOutcome()
    connection.execute("BEGIN IMMEDIATE")
    try:
        if not args.skip_inbox:
            replayed, inbox_failures = _replay_inbox(connection, inbox_plan, reset_mode)
            outcome.replayed = replayed
            outcome.inbox_failures.extend(inbox_failures)
        if args.resolve_audit_failed:
            resolved, audit_failures = _resolve_audit(connection, audit_plan)
            outcome.resolved = resolved
            outcome.audit_failures.extend(audit_failures)
        if outcome.failures:
            connection.execute("ROLLBACK")
            outcome.replayed = set()
            outcome.resolved = set()
        else:
            connection.execute("COMMIT")
            outcome.committed = True
    except sqlite3.Error as exc:
        connection.execute("ROLLBACK")
        outcome.replayed = set()
        outcome.resolved = set()
        outcome.error = f"写库失败已回滚: {exc}"
        logger.error("写库失败，已整体回滚: %s", exc)
    return outcome


if __name__ == "__main__":
    raise SystemExit(main())
