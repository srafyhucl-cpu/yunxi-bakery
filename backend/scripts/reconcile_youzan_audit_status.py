"""回写有赞 Webhook 审计终态：把 inbox 已确认 processed 的审计行补记为 processed。

背景
----
生产 `youzan_webhook_events` 里长期堆积 `status='received'` 的审计行。原因不是
业务没跑，而是**审计终态回写链路断了**：

- 审计行与 inbox 行按 `message_key = 'youzan_webhook:' || msg_id` 关联。生产
  实测：1668 条待回写审计行对应的 inbox 行 **100% 都是 `processed`**，
  但它们 inbox 载荷里的 `audit_id` **全为 NULL**；而 12827 条 `processed`
  审计行对应的 inbox 载荷都带 `audit_id`。
- worker 从 inbox 载荷里取 `audit_id` 回写审计
  （`webhook_dispatcher.py` → `audit_recorder.mark_*`）。`audit_id` 为 NULL 时
  这些标记静默跳过（`audit_helper.py`：`if audit_repo is None or audit_id is
  None: return`），于是**业务跑完了、inbox 是 processed，审计却永远停在
  `received`**——正是这 1668 行的 `process_stage` 全为空、
  `process_finished_at` 全为 NULL 的形态。
- 该形态在生产**仍在持续**：最近 24 小时仍新增 63 行 `received` 审计行，
  其 inbox 载荷的 `audit_id` 同样为 NULL。

本脚本只补记审计终态，**不修**上述链路缺陷（那属于服务侧改动，另案处理）。

判定口径（只认 inbox 事实，不猜）
---------------------------------
- `inbox_events.message_key = 'youzan_webhook:' || msg_id` 且该 inbox 行
  `status='processed'`：业务确实跑完了，**可以**回写审计为 `processed`，
  `process_stage='audit_backfilled'`，并补 `process_finished_at`/`updated_at`。
- inbox 行存在但状态是 `dead_letter`/`failed`/`processing`/`received`：
  处理结论不确定，**默认原样保留**，只进报告。
- 完全没有对应 inbox 行：无法证明处理结果，**默认原样保留**，只进报告，
  按事件类型与时间分桶统计，不做任何猜测。
- 只有显式传 `--mark-unmatched-skipped` 才会把上面两类「不能回写
  processed」的行标成 `skipped`，并在 `error_type` 写入稳定原因码。

第二重证据（只读，不参与判定）
----------------------------
`inbox processed` 只证明「worker 跑完」，不证明「业务写真的落地」：
`event_item` / `event_trade` 里存在若干「标记 FAILED 后直接 return、
不抛异常」的路径，这类行的 inbox 同样会变成 `processed`。因此报告额外
统计每个业务域在落地表（`youzan_orders` / `youzan_products` /
`member_balance`）中的命中情况，作为人工复核的第二重证据。
该维度**只进报告**，绝不据此改判；落地表缺失时记为 unavailable。

安全约束
--------
- 必须显式传 `--db`，脚本不猜测任何默认库路径；
- 默认 dry-run（以 SQLite `mode=ro` 打开，全程只读），只有 `--apply` 才写库；
- 路径疑似生产部署目录时必须额外传 `--allow-production`；
- `--older-than-hours`（默认 24）只处理「早于该阈值」的审计行，避免动到
  正在处理的新事件；
- 只更新 `youzan_webhook_events` 的审计状态列，**绝不**改 `inbox_events`、
  `member_balance`、`points_ledger`，也**绝不**删除任何行；
- 写库在单个事务内完成，任一行失败整体回滚，绝不部分写入；
- 报告字段固定、手机号脱敏。

时区口径
--------
审计表的 `received_at` 由 `app/utils.py:now_str()` 写入，用的是
`Asia/Shanghai` 北京时间；而 `inbox_events` 的时间列是 SQLite 的
`datetime('now')`（UTC）。两者相差 8 小时。本脚本所有阈值都按**北京时间**
计算（`ZoneInfo("Asia/Shanghai")`），再以绑定参数参与比较，避免把
UTC 口径当成北京时间而误判「新事件」。

用法
----
    # 只读核对（不写库）
    python scripts/reconcile_youzan_audit_status.py --db /path/to/bot.db

    # 核对通过后回写
    python scripts/reconcile_youzan_audit_status.py \
        --db /path/to/bot.db --apply

    # 指向生产路径时必须显式声明
    python scripts/reconcile_youzan_audit_status.py \
        --db /opt/apps/yunxi-bakery/backend/data/bot.db --apply --allow-production
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# 复用既有回放工具的生产路径判定与手机号脱敏口径，避免两套安全规则漂移。
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from resolve_youzan_dead_letters import (  # noqa: E402
    looks_like_production_path,
    mask_sensitive,
)

BEIJING_TZ = ZoneInfo("Asia/Shanghai")

# 审计表状态
AUDIT_RECEIVED = "received"
AUDIT_PROCESSED = "processed"
AUDIT_SKIPPED = "skipped"

# 回写用的稳定阶段码与稳定原因码
STAGE_BACKFILLED = "audit_backfilled"
STAGE_MARKED_SKIPPED = "audit_marked_skipped"

REASON_INBOX_PROCESSED = "inbox_processed"
REASON_INBOX_DEAD_LETTER = "inbox_dead_letter"
REASON_INBOX_FAILED = "inbox_failed"
REASON_INBOX_PROCESSING = "inbox_processing"
REASON_INBOX_RECEIVED = "inbox_received"
REASON_NO_INBOX = "no_inbox_record"

ERROR_TYPE_NO_INBOX = "audit_no_inbox_record"
ERROR_TYPE_DEAD_LETTER = "audit_inbox_dead_letter"
ERROR_TYPE_FAILED = "audit_inbox_failed"
ERROR_TYPE_PROCESSING = "audit_inbox_processing"
ERROR_TYPE_RECEIVED = "audit_inbox_received"

# 单条判定结论
DECISION_BACKFILL = "backfill_processed"
DECISION_MARK_SKIPPED = "mark_skipped"
DECISION_KEEP = "keep"

DEFAULT_OLDER_THAN_HOURS = 24
SAMPLE_LIMIT = 20
BUSINESS_TIMEOUT_MS = 15000

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REJECTED = 2

# 日志统一走 stderr，保证 stdout 只有一份可被机器解析的 JSON 报告。
logger = logging.getLogger("yunxi_bot.reconcile_youzan_audit_status")
logger.propagate = False


class TargetRejected(Exception):
    """目标库路径不满足安全前提。"""


@dataclass(frozen=True)
class AuditRow:
    """一条待判定的有赞审计行及其 inbox 对应状态。"""

    row_id: int
    msg_id: str
    event_type: str
    business_type: str
    business_key: str
    received_at: str
    inbox_status: str
    inbox_message_key: str


@dataclass(frozen=True)
class RowDecision:
    """单条审计行的判定结论。"""

    row: AuditRow
    decision: str
    reason: str
    write_status: str
    error_type: str
    error_message: str


@dataclass
class ReconciliationPlan:
    """整批审计行的回写计划。"""

    rows: list[AuditRow] = field(default_factory=list)
    decisions: list[RowDecision] = field(default_factory=list)
    recent_total: int = 0
    recent_by_event_type: dict[str, int] = field(default_factory=dict)
    audit_status_counts: dict[str, int] = field(default_factory=dict)
    business_evidence: dict[str, object] = field(default_factory=dict)

    def of(self, decision: str) -> list[RowDecision]:
        """按判定结论筛选。"""
        return [item for item in self.decisions if item.decision == decision]


@dataclass
class ApplyOutcome:
    """一次写库执行的结果。"""

    processed_written: int = 0
    skipped_written: int = 0
    failures: list[dict[str, object]] = field(default_factory=list)
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


def now_beijing() -> datetime:
    """返回当前北京时间（与 app/utils.py:now_str 同口径）。"""
    return datetime.now(BEIJING_TZ)


def format_beijing(moment: datetime) -> str:
    """把时间格式化成库内统一的字符串格式。"""
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def cutoff_at(older_than_hours: int) -> str:
    """计算审计行的时间阈值：早于该时刻的行才允许处理。"""
    moment = now_beijing() - timedelta(hours=older_than_hours)
    return format_beijing(moment)


AUDIT_JOIN_SQL = (
    "SELECT a.id, a.msg_id, a.event_type, a.business_type, a.business_key, "
    "a.received_at, "
    "COALESCE(i.status, '') AS inbox_status, "
    "COALESCE(i.message_key, '') AS inbox_message_key "
    "FROM youzan_webhook_events a "
    "LEFT JOIN inbox_events i "
    "ON i.message_key = 'youzan_webhook:' || a.msg_id "
    "AND i.queue_name = 'youzan_webhook' "
    "WHERE a.status = ? AND a.received_at < ? "
    "ORDER BY a.id"
)

RECENT_COUNT_SQL = (
    "SELECT COUNT(*) FROM youzan_webhook_events WHERE status = ? AND received_at >= ?"
)

RECENT_BY_EVENT_TYPE_SQL = (
    "SELECT event_type, COUNT(*) FROM youzan_webhook_events "
    "WHERE status = ? AND received_at >= ? GROUP BY event_type"
)

AUDIT_STATUS_COUNTS_SQL = (
    "SELECT status, COUNT(*) FROM youzan_webhook_events GROUP BY status"
)

BACKFILL_SQL = (
    "UPDATE youzan_webhook_events "
    "SET status = ?, process_stage = ?, process_finished_at = ?, updated_at = ? "
    "WHERE id = ? AND status = ?"
)

MARK_SKIPPED_SQL = (
    "UPDATE youzan_webhook_events "
    "SET status = ?, process_stage = ?, error_type = ?, error_message = ?, "
    "process_finished_at = ?, updated_at = ? "
    "WHERE id = ? AND status = ?"
)


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


def fetch_recent_summary(
    connection: sqlite3.Connection, *, status: str, cutoff: str
) -> tuple[int, dict[str, int]]:
    """统计落在阈值之内（不处理）的新审计行数量与事件类型分布。"""
    total = int(connection.execute(RECENT_COUNT_SQL, (status, cutoff)).fetchone()[0])
    by_event_type: dict[str, int] = {}
    for row in connection.execute(RECENT_BY_EVENT_TYPE_SQL, (status, cutoff)):
        key = str(row[0] or "")
        by_event_type[key or "(empty)"] = int(row[1])
    return total, dict(sorted(by_event_type.items()))


def fetch_status_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """统计审计表各状态数量。"""
    counts: dict[str, int] = {}
    for row in connection.execute(AUDIT_STATUS_COUNTS_SQL):
        counts[str(row[0] or "")] = int(row[1])
    return dict(sorted(counts.items()))


def fetch_candidate_rows(
    connection: sqlite3.Connection, *, status: str, cutoff: str
) -> list[AuditRow]:
    """读取早于阈值、且状态为 received 的审计行及其 inbox 对应状态。"""
    rows: list[AuditRow] = []
    for row in connection.execute(AUDIT_JOIN_SQL, (status, cutoff)):
        rows.append(
            AuditRow(
                row_id=int(row[0]),
                msg_id=str(row[1]),
                event_type=str(row[2] or ""),
                business_type=str(row[3] or ""),
                business_key=str(row[4] or ""),
                received_at=str(row[5] or ""),
                inbox_status=str(row[6] or ""),
                inbox_message_key=str(row[7] or ""),
            )
        )
    return rows


# ── 业务落地佐证（只读统计，用于报告，不参与判定）──────────────────────────
# inbox `processed` 只证明 worker 跑完，不足以证明业务写真的落地；
# 这里按业务域比对落地表，给出独立的第二重证据。
# 每条 SQL 都是写死的常量（表名/列名不参与拼接），业务值一律 ? 绑定。
EVIDENCE_TRADE_SQL = (
    "SELECT COUNT(DISTINCT a.id) AS total, "
    "COUNT(DISTINCT CASE WHEN o.order_no IS NOT NULL THEN a.id END) AS matched "
    "FROM youzan_webhook_events a "
    "LEFT JOIN youzan_orders o ON o.order_no = a.business_key "
    "WHERE a.status = ? AND a.received_at < ? AND a.business_type = ? "
    "AND a.business_key <> ''"
)

EVIDENCE_ITEM_SQL = (
    "SELECT COUNT(DISTINCT a.id) AS total, "
    "COUNT(DISTINCT CASE WHEN p.item_id IS NOT NULL THEN a.id END) AS matched "
    "FROM youzan_webhook_events a "
    "LEFT JOIN youzan_products p ON CAST(p.item_id AS TEXT) = a.business_key "
    "WHERE a.status = ? AND a.received_at < ? AND a.business_type = ? "
    "AND a.business_key <> ''"
)

EVIDENCE_MEMBER_SQL = (
    "SELECT COUNT(DISTINCT a.id) AS total, "
    "COUNT(DISTINCT CASE WHEN m.mobile IS NOT NULL THEN a.id END) AS matched "
    "FROM youzan_webhook_events a "
    "LEFT JOIN member_balance m ON m.mobile = a.business_key "
    "WHERE a.status = ? AND a.received_at < ? AND a.business_type = ? "
    "AND a.business_key <> ''"
)

EVIDENCE_SQL_BY_BUSINESS = {
    "trade": EVIDENCE_TRADE_SQL,
    "item": EVIDENCE_ITEM_SQL,
    "member": EVIDENCE_MEMBER_SQL,
}

EVIDENCE_TABLE_BY_BUSINESS = {
    "trade": "youzan_orders",
    "item": "youzan_products",
    "member": "member_balance",
}


def fetch_business_evidence(
    connection: sqlite3.Connection, *, status: str, cutoff: str
) -> dict[str, object]:
    """统计候选行在业务落地表中的佐证情况（只读，不参与判定）。

    目的：`inbox processed` 是「worker 跑完」的证据，不是「业务写落地」的
    证据。两者结合才能判断审计终态是否可以补记为 processed。
    落地表缺失时该维度记为 unavailable，绝不据此改判。
    """
    result: dict[str, object] = {"available": False, "by_business_type": {}}
    per_type: dict[str, dict[str, int]] = {}
    for business_type, sql in EVIDENCE_SQL_BY_BUSINESS.items():
        table = EVIDENCE_TABLE_BY_BUSINESS[business_type]
        if not _table_exists(connection, table):
            per_type[business_type] = {
                "total": 0,
                "with_business_evidence": 0,
                "available": 0,
            }
            continue
        row = connection.execute(sql, (status, cutoff, business_type)).fetchone()
        per_type[business_type] = {
            "total": int(row[0]),
            "with_business_evidence": int(row[1]),
            "available": 1,
        }
    result["available"] = any(item["available"] for item in per_type.values())
    result["by_business_type"] = per_type
    return result


def classify_row(row: AuditRow, *, mark_unmatched_skipped: bool) -> RowDecision:
    """判定单条审计行能否回写 processed。

    只有 inbox 明确 `processed` 才回写 processed；其余情形默认保留，
    仅在显式开启 `--mark-unmatched-skipped` 时才标 skipped。
    """
    if row.inbox_status == "processed":
        return RowDecision(
            row=row,
            decision=DECISION_BACKFILL,
            reason=REASON_INBOX_PROCESSED,
            write_status=AUDIT_PROCESSED,
            error_type="",
            error_message="",
        )

    if not row.inbox_status:
        reason = REASON_NO_INBOX
        error_type = ERROR_TYPE_NO_INBOX
        error_message = "没有对应的 inbox 记录，无法证明处理结果，默认保留"
    elif row.inbox_status == "dead_letter":
        reason = REASON_INBOX_DEAD_LETTER
        error_type = ERROR_TYPE_DEAD_LETTER
        error_message = "inbox 已进入死信，处理结论未确认，默认保留"
    elif row.inbox_status == "failed":
        reason = REASON_INBOX_FAILED
        error_type = ERROR_TYPE_FAILED
        error_message = "inbox 处理失败待重试，处理结论未确认，默认保留"
    elif row.inbox_status == "processing":
        reason = REASON_INBOX_PROCESSING
        error_type = ERROR_TYPE_PROCESSING
        error_message = "inbox 仍在处理中，处理结论未确认，默认保留"
    else:
        reason = REASON_INBOX_RECEIVED
        error_type = ERROR_TYPE_RECEIVED
        error_message = "inbox 仍在排队待处理，处理结论未确认，默认保留"

    if not mark_unmatched_skipped:
        return RowDecision(
            row=row,
            decision=DECISION_KEEP,
            reason=reason,
            write_status="",
            error_type="",
            error_message="",
        )
    return RowDecision(
        row=row,
        decision=DECISION_MARK_SKIPPED,
        reason=reason,
        write_status=AUDIT_SKIPPED,
        error_type=error_type,
        error_message=error_message,
    )


def build_plan(
    connection: sqlite3.Connection,
    *,
    status: str,
    cutoff: str,
    mark_unmatched_skipped: bool,
) -> ReconciliationPlan:
    """读取并逐条判定，形成回写计划。"""
    plan = ReconciliationPlan()
    plan.audit_status_counts = fetch_status_counts(connection)
    plan.recent_total, plan.recent_by_event_type = fetch_recent_summary(
        connection, status=status, cutoff=cutoff
    )
    plan.rows = fetch_candidate_rows(connection, status=status, cutoff=cutoff)
    plan.decisions = [
        classify_row(row, mark_unmatched_skipped=mark_unmatched_skipped)
        for row in plan.rows
    ]
    plan.business_evidence = fetch_business_evidence(
        connection, status=status, cutoff=cutoff
    )
    return plan


class BackfillFailed(Exception):
    """回写过程中存在失败行，需整体回滚。"""


def run_in_transaction(connection: sqlite3.Connection, work) -> None:
    """在单个事务内执行 work；work 抛错时整体回滚并向上抛。

    把「开事务—执行—提交/回滚」收敛到一处，保证任何异常路径都不会留下
    部分写入。回滚本身失败时只记录日志，不掩盖原始异常。
    """
    connection.execute("BEGIN IMMEDIATE")
    try:
        work()
    except Exception as exc:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error as rollback_exc:
            logger.error("回滚失败: %s", rollback_exc)
        logger.error("写库失败已整体回滚: %s", exc)
        raise
    connection.execute("COMMIT")


def apply_backfill(
    connection: sqlite3.Connection, plan: ReconciliationPlan
) -> ApplyOutcome:
    """在单个事务内执行回写。

    只更新 `youzan_webhook_events`；任一行失败整体回滚，绝不部分写入。
    """
    outcome = ApplyOutcome()
    finished_at = format_beijing(now_beijing())

    def write_all() -> None:
        """逐条执行回写；任何一行失败都记录后整体回滚。"""
        for decision in plan.of(DECISION_BACKFILL):
            try:
                cursor = connection.execute(
                    BACKFILL_SQL,
                    (
                        AUDIT_PROCESSED,
                        STAGE_BACKFILLED,
                        finished_at,
                        finished_at,
                        decision.row.row_id,
                        AUDIT_RECEIVED,
                    ),
                )
            except sqlite3.Error as exc:
                logger.error(
                    "回写审计 processed 失败 id=%s err=%s", decision.row.row_id, exc
                )
                outcome.failures.append(
                    {
                        "id": decision.row.row_id,
                        "reason": f"update_error: {exc}",
                    }
                )
                continue
            if int(cursor.rowcount or 0) != 1:
                outcome.failures.append(
                    {"id": decision.row.row_id, "reason": "status_changed_concurrently"}
                )
                continue
            outcome.processed_written += 1

        for decision in plan.of(DECISION_MARK_SKIPPED):
            try:
                cursor = connection.execute(
                    MARK_SKIPPED_SQL,
                    (
                        AUDIT_SKIPPED,
                        STAGE_MARKED_SKIPPED,
                        decision.error_type,
                        decision.error_message[:500],
                        finished_at,
                        finished_at,
                        decision.row.row_id,
                        AUDIT_RECEIVED,
                    ),
                )
            except sqlite3.Error as exc:
                logger.error(
                    "标记审计 skipped 失败 id=%s err=%s", decision.row.row_id, exc
                )
                outcome.failures.append(
                    {
                        "id": decision.row.row_id,
                        "reason": f"update_error: {exc}",
                    }
                )
                continue
            if int(cursor.rowcount or 0) != 1:
                outcome.failures.append(
                    {"id": decision.row.row_id, "reason": "status_changed_concurrently"}
                )
                continue
            outcome.skipped_written += 1

        if outcome.failures:
            raise BackfillFailed("存在更新失败行，本次回写已整体回滚")

    try:
        run_in_transaction(connection, write_all)
    except BackfillFailed as exc:
        outcome.processed_written = 0
        outcome.skipped_written = 0
        outcome.error = str(exc)
    except sqlite3.Error as exc:
        outcome.processed_written = 0
        outcome.skipped_written = 0
        outcome.error = f"写库失败已回滚: {exc}"
    else:
        outcome.committed = True
    return outcome


def _age_bucket(received_at: str, reference: datetime) -> str:
    """按接收时间距今多久给未匹配行分桶，用于按时间分类统计。"""
    try:
        moment = datetime.strptime(received_at, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=BEIJING_TZ
        )
    except (TypeError, ValueError):
        return "unknown"
    age_hours = int((reference - moment).total_seconds() // 3600)
    if age_hours < 0:
        return "future"
    if age_hours < 24:
        return "0-1d"
    if age_hours < 24 * 7:
        return "1-7d"
    if age_hours < 24 * 30:
        return "7-30d"
    return "30d+"


def _count_by(items: list[RowDecision], key: str) -> dict[str, int]:
    """按指定字段分组计数，结果按键排序。"""
    counts: dict[str, int] = {}
    for item in items:
        value = getattr(item.row, key) or ""
        label = value if value else "(empty)"
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _decision_row(decision: RowDecision) -> dict[str, object]:
    """把单条判定结论转成脱敏后的报告条目。"""
    row = decision.row
    return {
        "id": row.row_id,
        "msg_id": mask_sensitive(row.msg_id),
        "event_type": row.event_type or "(empty)",
        "business_type": row.business_type or "(empty)",
        "business_key": mask_sensitive(row.business_key),
        "received_at": row.received_at,
        "inbox_status": row.inbox_status or "(no_inbox)",
        "decision": decision.decision,
        "reason": decision.reason,
    }


def _sample_rows(decisions: list[RowDecision]) -> list[dict[str, object]]:
    """按判定结论各取样本，便于人工复核。"""
    samples: list[dict[str, object]] = []
    for decision_name in (DECISION_BACKFILL, DECISION_MARK_SKIPPED, DECISION_KEEP):
        picked = [item for item in decisions if item.decision == decision_name][
            :SAMPLE_LIMIT
        ]
        samples.extend(_decision_row(item) for item in picked)
    return samples


def build_report(
    plan: ReconciliationPlan,
    outcome: ApplyOutcome,
    *,
    mode: str,
    db_path: str,
    guard: dict[str, object],
    older_than_hours: int,
    cutoff: str,
    mark_unmatched_skipped: bool,
) -> dict[str, object]:
    """生成稳定结构的回写报告。"""
    by_decision: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    for decision in plan.decisions:
        by_decision[decision.decision] = by_decision.get(decision.decision, 0) + 1
        by_reason[decision.reason] = by_reason.get(decision.reason, 0) + 1

    keep_rows = plan.of(DECISION_KEEP)
    unmatched = [item for item in plan.decisions if item.reason == REASON_NO_INBOX]
    reference = now_beijing()
    unmatched_by_age: dict[str, int] = {}
    for item in unmatched:
        bucket = _age_bucket(item.row.received_at, reference)
        unmatched_by_age[bucket] = unmatched_by_age.get(bucket, 0) + 1

    inbox_status_counts: dict[str, int] = {}
    for row in plan.rows:
        label = row.inbox_status or "(no_inbox)"
        inbox_status_counts[label] = inbox_status_counts.get(label, 0) + 1

    status = "ok"
    if outcome.error:
        status = "failed"
    report: dict[str, object] = {
        "status": status,
        "mode": mode,
        "db": db_path,
        "run_at": format_beijing(reference),
        "production_guard": guard,
        "options": {
            "older_than_hours": older_than_hours,
            "cutoff_at": cutoff,
            "mark_unmatched_skipped": mark_unmatched_skipped,
        },
        "scope": {
            "audit_status_counts": plan.audit_status_counts,
            "candidate_total": len(plan.rows),
            "recent_kept_total": plan.recent_total,
            "recent_kept_by_event_type": plan.recent_by_event_type,
        },
        "stats": {
            "by_event_type": _count_by(plan.decisions, "event_type"),
            "by_business_type": _count_by(plan.decisions, "business_type"),
            "by_inbox_status": dict(sorted(inbox_status_counts.items())),
            "by_decision": dict(sorted(by_decision.items())),
            "by_reason": dict(sorted(by_reason.items())),
            "unmatched_by_event_type": _count_by(unmatched, "event_type"),
            "unmatched_by_age_bucket": dict(sorted(unmatched_by_age.items())),
            "business_evidence": plan.business_evidence,
        },
        "plan": {
            "will_processed": len(plan.of(DECISION_BACKFILL)),
            "will_skipped": len(plan.of(DECISION_MARK_SKIPPED)),
            "will_keep": len(keep_rows),
        },
        "result": {
            "processed_written": outcome.processed_written,
            "skipped_written": outcome.skipped_written,
            "failures": outcome.failures,
            "committed": outcome.committed,
            "error": outcome.error,
        },
        "samples": _sample_rows(plan.decisions),
        "summary": {
            "candidate_total": len(plan.rows),
            "recent_kept_total": plan.recent_total,
            "would_processed": len(plan.of(DECISION_BACKFILL)),
            "would_skipped": len(plan.of(DECISION_MARK_SKIPPED)),
            "kept": len(keep_rows),
            "processed_written": outcome.processed_written,
            "skipped_written": outcome.skipped_written,
            "committed": outcome.committed,
        },
    }
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数；默认 dry-run，不写库。"""
    parser = argparse.ArgumentParser(
        description="把 inbox 已确认 processed 的有赞审计行回写为 processed"
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
        "--older-than-hours",
        type=int,
        default=DEFAULT_OLDER_THAN_HOURS,
        help=(
            "只处理早于该小时数的审计行（按北京时间，默认 24），"
            "避免动到正在处理的新事件。"
        ),
    )
    parser.add_argument(
        "--mark-unmatched-skipped",
        action="store_true",
        help=(
            "把无法回写 processed 的行（无 inbox 记录，或 inbox 未 processed）"
            "显式标记为 skipped；不加该参数时只报告、原样保留。"
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


def main(argv: list[str] | None = None) -> int:
    """脚本入口，返回进程退出码。"""
    _configure_logging()
    args = parse_args(argv)
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
    if args.older_than_hours < 0:
        report["status"] = "rejected"
        report["error"] = "--older-than-hours 不能为负数"
        report["summary"] = {"rejected": True}
        emit_report(report, args.output)
        logger.error("--older-than-hours 不能为负数")
        return EXIT_REJECTED

    cutoff = cutoff_at(args.older_than_hours)
    try:
        with closing(_connect(db_path, read_only=not args.apply)) as connection:
            return _run_on_database(connection, args, report, cutoff)
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
    cutoff: str,
) -> int:
    """在目标库上完成核对、回写与报告输出。"""
    missing_tables = [
        name
        for name in ("youzan_webhook_events", "inbox_events")
        if not _table_exists(connection, name)
    ]
    if missing_tables:
        report["status"] = "failed"
        report["error"] = f"目标库缺少必要的表: {', '.join(missing_tables)}"
        report["summary"] = {"missing_tables": missing_tables}
        emit_report(report, args.output)
        logger.error("目标库缺少必要的表: %s", ", ".join(missing_tables))
        return EXIT_FAILED

    plan = build_plan(
        connection,
        status=AUDIT_RECEIVED,
        cutoff=cutoff,
        mark_unmatched_skipped=bool(args.mark_unmatched_skipped),
    )

    outcome = ApplyOutcome()
    if args.apply:
        outcome = apply_backfill(connection, plan)

    guard = report.get("production_guard", {})
    if not isinstance(guard, dict):
        guard = {}
    report.update(
        build_report(
            plan,
            outcome,
            mode="apply" if args.apply else "dry-run",
            db_path=str(args.db),
            guard=guard,
            older_than_hours=int(args.older_than_hours),
            cutoff=cutoff,
            mark_unmatched_skipped=bool(args.mark_unmatched_skipped),
        )
    )
    emit_report(report, args.output)
    logger.info(
        "核对完成 mode=%s candidate=%s would_processed=%s kept=%s written_processed=%s",
        report["mode"],
        len(plan.rows),
        len(plan.of(DECISION_BACKFILL)),
        len(plan.of(DECISION_KEEP)),
        outcome.processed_written,
    )
    if outcome.error:
        logger.error("回写未完成: %s", outcome.error)
        return EXIT_FAILED
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
