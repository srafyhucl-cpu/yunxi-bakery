"""Repository for observability content change history."""

from app.models.content_change_history import (
    ContentChangeHistoryCreate,
    ContentChangeHistoryEntry,
)


from app.repository.base import BaseRepository


class ContentChangeHistoryRepo(BaseRepository):
    """Stores append-only content change records."""

    async def add(self, entry: ContentChangeHistoryCreate) -> int:
        cursor = await self._db.execute(
            "INSERT INTO content_change_history ("
            "entity_type, entity_key, category, title, source, source_ref, "
            "session_id, webhook_msg_id, action, status, change_summary_json, "
            "error_type, error_message, occurred_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.entity_type,
                entry.entity_key,
                entry.category,
                entry.title,
                entry.source,
                entry.source_ref,
                entry.session_id,
                entry.webhook_msg_id,
                entry.action,
                entry.status,
                entry.change_summary_json,
                entry.error_type,
                entry.error_message,
                entry.occurred_at,
            ),
        )
        await self._db.commit()
        return int(cursor.lastrowid)

    async def list_entries(
        self,
        *,
        date_from: str = "",
        date_to: str = "",
        source: str = "",
        status: str = "",
        entity_type: str = "",
        keyword: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[ContentChangeHistoryEntry]:
        clauses = ["1 = 1"]
        params: list[object] = []
        if date_from:
            clauses.append("c.occurred_at >= ?")
            params.append(f"{date_from} 00:00:00")
        if date_to:
            clauses.append("c.occurred_at <= ?")
            params.append(f"{date_to} 23:59:59")
        if source:
            clauses.append("c.source = ?")
            params.append(source)
        if status:
            clauses.append("c.status = ?")
            params.append(status)
        if entity_type:
            clauses.append("c.entity_type = ?")
            params.append(entity_type)
        if keyword:
            like = f"%{keyword}%"
            clauses.append(
                "(c.title LIKE ? OR c.entity_key LIKE ? OR c.change_summary_json LIKE ?)"
            )
            params.extend([like, like, like])
        rows = await self._db.execute_fetchall(
            "SELECT c.id, c.entity_type, c.entity_key, c.category, c.title, c.source, c.source_ref, "
            "c.session_id, c.webhook_msg_id, c.action, c.status, c.change_summary_json, "
            "c.error_type, c.error_message, c.occurred_at, "
            "w.event_type AS webhook_event_type "
            "FROM content_change_history c "
            "LEFT JOIN youzan_webhook_events w ON c.webhook_msg_id = w.msg_id "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY c.occurred_at DESC, c.id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return [ContentChangeHistoryEntry(**dict(row)) for row in rows]

    async def count_entries(
        self,
        *,
        date_from: str = "",
        date_to: str = "",
        source: str = "",
        status: str = "",
        entity_type: str = "",
        keyword: str = "",
    ) -> int:
        clauses = ["1 = 1"]
        params: list[object] = []
        if date_from:
            clauses.append("occurred_at >= ?")
            params.append(f"{date_from} 00:00:00")
        if date_to:
            clauses.append("occurred_at <= ?")
            params.append(f"{date_to} 23:59:59")
        if source:
            clauses.append("source = ?")
            params.append(source)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if entity_type:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        if keyword:
            like = f"%{keyword}%"
            clauses.append(
                "(title LIKE ? OR entity_key LIKE ? OR change_summary_json LIKE ?)"
            )
            params.extend([like, like, like])
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) AS c FROM content_change_history "
            f"WHERE {' AND '.join(clauses)}",
            tuple(params),
        )
        return int(rows[0]["c"]) if rows else 0

    async def get_by_id(self, entry_id: int) -> ContentChangeHistoryEntry | None:
        rows = await self._db.execute_fetchall(
            "SELECT c.id, c.entity_type, c.entity_key, c.category, c.title, c.source, c.source_ref, "
            "c.session_id, c.webhook_msg_id, c.action, c.status, c.change_summary_json, "
            "c.error_type, c.error_message, c.occurred_at, "
            "w.event_type AS webhook_event_type "
            "FROM content_change_history c "
            "LEFT JOIN youzan_webhook_events w ON c.webhook_msg_id = w.msg_id "
            "WHERE c.id = ?",
            (entry_id,),
        )
        return ContentChangeHistoryEntry(**dict(rows[0])) if rows else None

    async def list_for_entity(
        self,
        *,
        entity_type: str,
        entity_key: str,
        limit: int = 20,
    ) -> list[ContentChangeHistoryEntry]:
        rows = await self._db.execute_fetchall(
            "SELECT c.id, c.entity_type, c.entity_key, c.category, c.title, c.source, c.source_ref, "
            "c.session_id, c.webhook_msg_id, c.action, c.status, c.change_summary_json, "
            "c.error_type, c.error_message, c.occurred_at, "
            "w.event_type AS webhook_event_type "
            "FROM content_change_history c "
            "LEFT JOIN youzan_webhook_events w ON c.webhook_msg_id = w.msg_id "
            "WHERE c.entity_type = ? AND c.entity_key = ? "
            "ORDER BY c.occurred_at DESC, c.id DESC LIMIT ?",
            (entity_type, entity_key, limit),
        )
        return [ContentChangeHistoryEntry(**dict(row)) for row in rows]
