"""有赞 Webhook 审计事件的数据访问层。"""

from datetime import datetime

from app.models.youzan_webhook_event import (
    YouzanWebhookEventCreate,
    YouzanWebhookEventUpdate,
    YouzanWebhookStatus,
)
from app.repository.base import BaseRepository
from app.utils import now_str


class YouzanWebhookEventRepo(BaseRepository):
    """存储每个接收到的有赞 Webhook 的持久审计追踪。"""

    async def create_received(self, event: YouzanWebhookEventCreate) -> int:
        now = now_str()
        await self._db.execute(
            "INSERT INTO youzan_webhook_events ("
            "msg_id, trace_id, event_type, business_type, business_key, status, "
            "http_status, received_at, payload_hash, payload_summary_json, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(msg_id) DO UPDATE SET "
            "    status = ?, "
            "    trace_id = excluded.trace_id, "
            "    event_type = excluded.event_type, "
            "    business_type = excluded.business_type, "
            "    business_key = excluded.business_key, "
            "    http_status = excluded.http_status, "
            "    payload_hash = excluded.payload_hash, "
            "    payload_summary_json = excluded.payload_summary_json, "
            "    updated_at = excluded.updated_at",
            (
                event.msg_id,
                event.trace_id,
                event.event_type,
                event.business_type,
                event.business_key,
                YouzanWebhookStatus.RECEIVED,
                event.http_status,
                now,
                event.payload_hash,
                event.payload_summary_json,
                now,
                now,
                YouzanWebhookStatus.DUPLICATE,
            ),
        )
        await self._db.commit()
        row = await self._db.execute_fetchall(
            "SELECT id FROM youzan_webhook_events WHERE msg_id = ?",
            (event.msg_id,),
        )
        return int(row[0]["id"])

    async def mark_processing(
        self,
        event_id: int,
        process_stage: str = "dispatched",
        business_type: str | None = None,
        business_key: str = "",
    ) -> None:
        now = now_str()
        await self._db.execute(
            "UPDATE youzan_webhook_events SET status = ?, process_stage = ?, "
            "business_type = COALESCE(?, business_type), "
            "business_key = COALESCE(NULLIF(?, ''), business_key), "
            "process_started_at = COALESCE(process_started_at, ?), updated_at = ? "
            "WHERE id = ?",
            (
                YouzanWebhookStatus.PROCESSING,
                process_stage,
                business_type,
                business_key,
                now,
                now,
                event_id,
            ),
        )
        await self._db.commit()

    async def mark_result(
        self, event_id: int, update: YouzanWebhookEventUpdate
    ) -> None:
        now = now_str()
        rows = await self._db.execute_fetchall(
            "SELECT process_started_at FROM youzan_webhook_events WHERE id = ?",
            (event_id,),
        )
        started_at = rows[0]["process_started_at"] if rows else None
        duration_ms = _duration_ms(started_at, now) if started_at else None
        await self._db.execute(
            "UPDATE youzan_webhook_events SET "
            "status = ?, process_stage = ?, "
            "business_type = COALESCE(?, business_type), "
            "business_key = COALESCE(NULLIF(?, ''), business_key), "
            "error_type = ?, error_message = ?, "
            "process_finished_at = ?, duration_ms = ?, updated_at = ? "
            "WHERE id = ?",
            (
                update.status,
                update.process_stage,
                update.business_type,
                update.business_key,
                update.error_type,
                update.error_message,
                now,
                duration_ms,
                now,
                event_id,
            ),
        )
        await self._db.commit()

    async def get_by_msg_id(self, msg_id: str) -> dict | None:
        rows = await self._db.execute_fetchall(
            "SELECT id, msg_id, trace_id, event_type, business_type, business_key, "
            "status, http_status, process_stage, error_type, error_message, "
            "payload_summary_json, received_at, process_started_at, process_finished_at, duration_ms "
            "FROM youzan_webhook_events WHERE msg_id = ?",
            (msg_id,),
        )
        return dict(rows[0]) if rows else None

    async def list_events(
        self,
        *,
        status: str = "",
        event_type: str = "",
        keyword: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses = ["1 = 1"]
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if date_from:
            clauses.append("received_at >= ?")
            params.append(f"{date_from} 00:00:00")
        if date_to:
            clauses.append("received_at <= ?")
            params.append(f"{date_to} 23:59:59")
        if keyword:
            like = f"%{keyword}%"
            clauses.append(
                "(msg_id LIKE ? OR business_key LIKE ? OR error_message LIKE ? OR payload_summary_json LIKE ?)"
            )
            params.extend([like, like, like, like])
        rows = await self._db.execute_fetchall(
            "SELECT id, msg_id, trace_id, event_type, business_type, business_key, "
            "status, http_status, process_stage, error_type, error_message, payload_summary_json, "
            "received_at, process_started_at, process_finished_at, duration_ms "
            "FROM youzan_webhook_events "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY received_at DESC, id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return [dict(row) for row in rows]

    async def count_events(
        self,
        *,
        status: str = "",
        event_type: str = "",
        keyword: str = "",
        date_from: str = "",
        date_to: str = "",
    ) -> int:
        clauses = ["1 = 1"]
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if date_from:
            clauses.append("received_at >= ?")
            params.append(f"{date_from} 00:00:00")
        if date_to:
            clauses.append("received_at <= ?")
            params.append(f"{date_to} 23:59:59")
        if keyword:
            like = f"%{keyword}%"
            clauses.append(
                "(msg_id LIKE ? OR business_key LIKE ? OR error_message LIKE ? OR payload_summary_json LIKE ?)"
            )
            params.extend([like, like, like, like])
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) AS c FROM youzan_webhook_events "
            f"WHERE {' AND '.join(clauses)}",
            tuple(params),
        )
        return int(rows[0]["c"]) if rows else 0

    async def get_by_id(self, event_id: int) -> dict | None:
        rows = await self._db.execute_fetchall(
            "SELECT id, msg_id, trace_id, event_type, business_type, business_key, "
            "status, http_status, process_stage, error_type, error_message, payload_summary_json, "
            "received_at, process_started_at, process_finished_at, duration_ms "
            "FROM youzan_webhook_events WHERE id = ?",
            (event_id,),
        )
        return dict(rows[0]) if rows else None


def _duration_ms(started_at: str, finished_at: str) -> int:
    started = datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S")
    finished = datetime.strptime(finished_at, "%Y-%m-%d %H:%M:%S")
    return max(0, int((finished - started).total_seconds() * 1000))
