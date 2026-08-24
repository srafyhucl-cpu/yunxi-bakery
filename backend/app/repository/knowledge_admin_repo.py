"""知识库后台管理数据访问层。

职责：FAQ/规则/话术类知识条目的 CRUD 操作（管理后台专用）。
"""

from app.models.content_change_history import WriteResult
from app.models.knowledge import (
    KnowledgeAudience,
    KnowledgeEntry,
    KnowledgeReviewStatus,
    VectorSyncStatus,
)
from app.repository.base import BaseRepository
from app.repository.knowledge_repo import ENTRY_SELECT_SQL

ADMIN_LIST_CONTENT_TYPES = ("faq", "rule", "script")
ADMIN_ENTRY_INSERT_SQL = (
    "INSERT INTO knowledge_base ("
    "category, content_type, title, content, keywords, priority, is_active, "
    "last_sync_source, last_sync_ref, content_origin, created_by, updated_by, "
    "suggested_category, suggest_reason, vector_sync_status, vector_sync_error, "
    "vector_synced_at, vector_sync_retry_count, audience, review_status, "
    "valid_from, valid_until, reviewed_by, reviewed_at"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', 0, ?, ?, ?, ?, ?, ?)"
)
ADMIN_ENTRY_UPDATE_SQL = (
    "UPDATE knowledge_base SET "
    "category = ?, content_type = ?, title = ?, content = ?, keywords = ?, priority = ?, "
    "is_active = ?, updated_by = ?, suggested_category = ?, suggest_reason = ?, "
    "last_sync_source = ?, last_sync_ref = ?, vector_sync_status = ?, "
    "audience = ?, review_status = ?, valid_from = ?, valid_until = ?, "
    "reviewed_by = ?, reviewed_at = ?, "
    "vector_sync_error = '', vector_synced_at = '', updated_at = datetime('now') "
    "WHERE id = ?"
)


class KnowledgeAdminRepo(BaseRepository):
    """后台知识配置仓库：负责 FAQ/规则/话术的分页、增删改查。"""

    async def list_admin_entries(
        self,
        *,
        content_type: str = "",
        keyword: str = "",
        is_active: str = "",
        vector_status: str = "",
        limit: int = 30,
        offset: int = 0,
    ) -> list[KnowledgeEntry]:
        """分页获取后台知识配置列表。"""
        clauses = ["content_type IN (?, ?, ?)", "category != 'product'"]
        params: list[object] = list(ADMIN_LIST_CONTENT_TYPES)
        if content_type:
            clauses.append("content_type = ?")
            params.append(content_type)
        if keyword:
            like = f"%{keyword}%"
            clauses.append(
                "(title LIKE ? OR content LIKE ? OR keywords LIKE ? OR vector_sync_error LIKE ?)"
            )
            params.extend([like, like, like, like])
        if is_active in {"0", "1"}:
            clauses.append("is_active = ?")
            params.append(int(is_active))
        if vector_status:
            clauses.append("vector_sync_status = ?")
            params.append(vector_status)
        rows = await self._db.execute_fetchall(
            ENTRY_SELECT_SQL
            + f"WHERE {' AND '.join(clauses)} "
            + "ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return [KnowledgeEntry(**dict(row)) for row in rows]

    async def count_admin_entries(
        self,
        *,
        content_type: str = "",
        keyword: str = "",
        is_active: str = "",
        vector_status: str = "",
    ) -> int:
        """返回后台知识配置列表总数。"""
        clauses = ["content_type IN (?, ?, ?)", "category != 'product'"]
        params: list[object] = list(ADMIN_LIST_CONTENT_TYPES)
        if content_type:
            clauses.append("content_type = ?")
            params.append(content_type)
        if keyword:
            like = f"%{keyword}%"
            clauses.append(
                "(title LIKE ? OR content LIKE ? OR keywords LIKE ? OR vector_sync_error LIKE ?)"
            )
            params.extend([like, like, like, like])
        if is_active in {"0", "1"}:
            clauses.append("is_active = ?")
            params.append(int(is_active))
        if vector_status:
            clauses.append("vector_sync_status = ?")
            params.append(vector_status)
        where_sql = " AND ".join(clauses)
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) AS c FROM knowledge_base WHERE " + where_sql,
            tuple(params),
        )
        return int(rows[0]["c"]) if rows else 0

    async def create_admin_entry(
        self,
        *,
        category: str,
        content_type: str,
        title: str,
        content: str,
        keywords: str,
        priority: int,
        is_active: bool,
        content_origin: str,
        created_by: str,
        updated_by: str,
        suggested_category: str,
        suggest_reason: str,
        sync_source: str,
        sync_ref: str = "",
        vector_sync_status: str = VectorSyncStatus.PENDING,
        audience: str = KnowledgeAudience.ALL.value,
        review_status: str = KnowledgeReviewStatus.PUBLISHED.value,
        valid_from: str = "",
        valid_until: str = "",
        reviewed_by: str = "",
        reviewed_at: str = "",
    ) -> int:
        """插入一条后台知识配置记录。"""
        cursor = await self._db.execute(
            ADMIN_ENTRY_INSERT_SQL,
            _build_create_admin_entry_params(locals()),
        )
        await self._db.commit()
        return int(cursor.lastrowid)

    async def update_admin_entry(
        self,
        entry_id: int,
        *,
        category: str,
        content_type: str,
        title: str,
        content: str,
        keywords: str,
        priority: int,
        is_active: bool,
        updated_by: str,
        suggested_category: str,
        suggest_reason: str,
        sync_source: str,
        sync_ref: str = "",
        vector_sync_status: str = VectorSyncStatus.PENDING,
        audience: str = KnowledgeAudience.ALL.value,
        review_status: str = KnowledgeReviewStatus.PUBLISHED.value,
        valid_from: str = "",
        valid_until: str = "",
        reviewed_by: str = "",
        reviewed_at: str = "",
    ) -> str:
        """更新后台知识配置记录。"""
        cursor = await self._db.execute(
            ADMIN_ENTRY_UPDATE_SQL,
            _build_update_admin_entry_params(locals()),
        )
        await self._db.commit()
        return WriteResult.APPLIED if cursor.rowcount else WriteResult.SKIPPED

    async def update_active(
        self,
        entry_id: int,
        is_active: bool,
        *,
        sync_source: str = "",
        sync_ref: str = "",
    ) -> str:
        """更新条目启用状态，并记录最后修改来源。"""
        cursor = await self._db.execute(
            "UPDATE knowledge_base SET is_active = ?, "
            "last_sync_source = CASE WHEN ? != '' THEN ? ELSE last_sync_source END, "
            "last_sync_ref = CASE WHEN ? != '' THEN ? ELSE last_sync_ref END, "
            "updated_at = datetime('now') WHERE id = ?",
            (
                1 if is_active else 0,
                sync_source,
                sync_source,
                sync_ref,
                sync_ref,
                entry_id,
            ),
        )
        await self._db.commit()
        return WriteResult.APPLIED if cursor.rowcount else WriteResult.SKIPPED


def _build_create_admin_entry_params(values: dict[str, object]) -> tuple[object, ...]:
    return (
        values["category"],
        values["content_type"],
        values["title"],
        values["content"],
        values["keywords"],
        values["priority"],
        1 if values["is_active"] else 0,
        values["sync_source"],
        values["sync_ref"],
        values["content_origin"],
        values["created_by"],
        values["updated_by"],
        values["suggested_category"],
        values["suggest_reason"],
        values["vector_sync_status"],
        values["audience"],
        values["review_status"],
        values["valid_from"],
        values["valid_until"],
        values["reviewed_by"],
        values["reviewed_at"],
    )


def _build_update_admin_entry_params(values: dict[str, object]) -> tuple[object, ...]:
    return (
        values["category"],
        values["content_type"],
        values["title"],
        values["content"],
        values["keywords"],
        values["priority"],
        1 if values["is_active"] else 0,
        values["updated_by"],
        values["suggested_category"],
        values["suggest_reason"],
        values["sync_source"],
        values["sync_ref"],
        values["vector_sync_status"],
        values["audience"],
        values["review_status"],
        values["valid_from"],
        values["valid_until"],
        values["reviewed_by"],
        values["reviewed_at"],
        values["entry_id"],
    )
