"""知识库 RAG 检索、通用查询与向量同步数据访问层。"""

import json

from app.models.content_change_history import WriteResult
from app.models.knowledge import (
    KnowledgeAudience,
    KnowledgeEntry,
    KnowledgeReviewStatus,
    VectorSyncStatus,
)
from app.models.knowledge_retrieval_log import (
    KnowledgeRetrievalLog,
    KnowledgeRetrievalLogCreate,
)
from app.repository.base import BaseRepository

ENTRY_COLUMNS = (
    "id, category, content_type, title, content, keywords, priority, is_active, "
    "youzan_item_id, last_sync_source, last_sync_ref, content_origin, created_by, "
    "updated_by, suggested_category, suggest_reason, vector_sync_status, "
    "vector_synced_at, vector_sync_error, vector_sync_retry_count, audience, "
    "review_status, valid_from, valid_until, reviewed_by, reviewed_at, created_at, updated_at"
)
ENTRY_SELECT_SQL = "SELECT " + ENTRY_COLUMNS + " FROM knowledge_base "
PUBLISHED_KNOWLEDGE_FILTER_SQL = (
    "review_status = ? "
    "AND (valid_from = '' OR valid_from <= datetime('now')) "
    "AND (valid_until = '' OR valid_until >= datetime('now')) "
)
KNOWLEDGE_INSERT_SQL = (
    "INSERT INTO knowledge_base ("
    "category, content_type, title, content, keywords, priority, is_active, "
    "last_sync_source, last_sync_ref, content_origin, created_by, updated_by, "
    "suggested_category, suggest_reason, vector_sync_status, vector_synced_at, "
    "audience, review_status, valid_from, valid_until, reviewed_by, reviewed_at"
    ") VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
RETRIEVAL_LOG_COLUMNS = (
    "id, bot_type, audience, query, query_hash, query_category, retrieval_mode, "
    "matched_entry_ids_json, matched_titles_json, result_count, fallback_reason, "
    "created_at"
)
RETRIEVAL_LOG_INSERT_SQL = (
    "INSERT INTO knowledge_retrieval_logs ("
    "bot_type, audience, query, query_hash, query_category, retrieval_mode, "
    "matched_entry_ids_json, matched_titles_json, result_count, fallback_reason"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


class KnowledgeRepo(BaseRepository):
    """知识库仓库：提供检索、管理和商品知识回写能力。"""

    async def search(
        self,
        query: str,
        limit: int = 5,
        *,
        audience: str = KnowledgeAudience.ALL.value,
    ) -> list[KnowledgeEntry]:
        """按关键词搜索启用中的知识条目。"""
        keyword = f"%{query}%"
        governance_sql, governance_params = _build_governance_filter(audience)
        rows = await self._db.execute_fetchall(
            ENTRY_SELECT_SQL
            + "WHERE is_active = 1 AND "
            + governance_sql
            + " AND (title LIKE ? OR content LIKE ? OR keywords LIKE ?) "
            + "ORDER BY priority DESC LIMIT ?",
            (*governance_params, keyword, keyword, keyword, limit),
        )
        return [KnowledgeEntry(**dict(row)) for row in rows]

    async def get_by_category(
        self,
        category: str,
        *,
        audience: str = KnowledgeAudience.ALL.value,
    ) -> list[KnowledgeEntry]:
        """按检索分类获取启用中的知识条目。"""
        governance_sql, governance_params = _build_governance_filter(audience)
        rows = await self._db.execute_fetchall(
            ENTRY_SELECT_SQL
            + "WHERE category = ? AND is_active = 1 AND "
            + governance_sql
            + " "
            + "ORDER BY priority DESC",
            (category, *governance_params),
        )
        return [KnowledgeEntry(**dict(row)) for row in rows]

    async def get_by_titles(
        self,
        titles: list[str],
        limit: int = 8,
        *,
        audience: str = KnowledgeAudience.ALL.value,
    ) -> list[KnowledgeEntry]:
        """根据标题批量获取知识条目。"""
        if not titles:
            return []
        governance_sql, governance_params = _build_governance_filter(audience)
        placeholders = ",".join("?" * len(titles))
        rows = await self._db.execute_fetchall(
            ENTRY_SELECT_SQL
            + f"WHERE title IN ({placeholders}) AND is_active = 1 AND "
            + governance_sql
            + " "
            + "ORDER BY priority DESC LIMIT ?",
            (*titles, *governance_params, limit),
        )
        return [KnowledgeEntry(**dict(row)) for row in rows]

    async def get_by_youzan_item_ids(
        self,
        keys: list[str],
        limit: int = 8,
        *,
        audience: str = KnowledgeAudience.ALL.value,
    ) -> list[KnowledgeEntry]:
        """根据有赞商品 ID 或本地知识 ID 批量获取知识条目。"""
        if not keys:
            return []

        youzan_ids: list[str] = []
        knowledge_ids: list[int] = []
        for key in keys:
            if key.startswith("kb_"):
                try:
                    knowledge_ids.append(int(key[3:]))
                except ValueError:
                    continue
            else:
                youzan_ids.append(key)

        clauses: list[str] = []
        params: list[object] = []
        if youzan_ids:
            placeholders = ",".join("?" * len(youzan_ids))
            clauses.append(f"youzan_item_id IN ({placeholders})")
            params.extend(youzan_ids)
        if knowledge_ids:
            placeholders = ",".join("?" * len(knowledge_ids))
            clauses.append(f"id IN ({placeholders})")
            params.extend(knowledge_ids)
        if not clauses:
            return []

        governance_sql, governance_params = _build_governance_filter(audience)
        rows = await self._db.execute_fetchall(
            ENTRY_SELECT_SQL
            + f"WHERE ({' OR '.join(clauses)}) AND is_active = 1 AND "
            + governance_sql
            + " "
            + "ORDER BY priority DESC LIMIT ?",
            (*params, *governance_params, limit),
        )
        return [KnowledgeEntry(**dict(row)) for row in rows]

    async def get_all_titles(
        self, *, audience: str = KnowledgeAudience.ALL.value
    ) -> list[tuple[str, str]]:
        """获取全部启用知识的标题与正文。"""
        governance_sql, governance_params = _build_governance_filter(audience)
        rows = await self._db.execute_fetchall(
            "SELECT title, content FROM knowledge_base WHERE is_active = 1 AND "
            + governance_sql,
            tuple(governance_params),
        )
        return [(row["title"], row["content"]) for row in rows]

    async def get_all_titles_with_keys(
        self, *, audience: str = KnowledgeAudience.ALL.value
    ) -> list[tuple[str, str, str]]:
        """获取全部启用知识，供向量索引构建使用。"""
        governance_sql, governance_params = _build_governance_filter(audience)
        rows = await self._db.execute_fetchall(
            "SELECT id, youzan_item_id, title, content FROM knowledge_base "
            "WHERE is_active = 1 AND " + governance_sql,
            tuple(governance_params),
        )
        return [
            (
                row["youzan_item_id"] if row["youzan_item_id"] else f"kb_{row['id']}",
                row["title"],
                row["content"],
            )
            for row in rows
        ]

    async def count_all(self) -> int:
        """返回知识库总条目数。"""
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) AS c FROM knowledge_base"
        )
        return int(rows[0]["c"]) if rows else 0

    async def list_current_entries(
        self,
        *,
        category: str = "",
        keyword: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[KnowledgeEntry]:
        """分页获取当前知识内容，供观察台使用。"""
        clauses = ["1 = 1"]
        params: list[object] = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if keyword:
            like = f"%{keyword}%"
            clauses.append("(title LIKE ? OR content LIKE ? OR keywords LIKE ?)")
            params.extend([like, like, like])
        rows = await self._db.execute_fetchall(
            ENTRY_SELECT_SQL
            + f"WHERE {' AND '.join(clauses)} "
            + "ORDER BY updated_at DESC, priority DESC, id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return [KnowledgeEntry(**dict(row)) for row in rows]

    async def count_current_entries(
        self, *, category: str = "", keyword: str = ""
    ) -> int:
        """返回观察台当前知识总数。"""
        clauses = ["1 = 1"]
        params: list[object] = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if keyword:
            like = f"%{keyword}%"
            clauses.append("(title LIKE ? OR content LIKE ? OR keywords LIKE ?)")
            params.extend([like, like, like])
        where_sql = " AND ".join(clauses)
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) AS c FROM knowledge_base WHERE " + where_sql,
            tuple(params),
        )
        return int(rows[0]["c"]) if rows else 0

    async def get_by_id(self, entry_id: int) -> KnowledgeEntry | None:
        """按 ID 获取单条知识记录。"""
        rows = await self._db.execute_fetchall(
            ENTRY_SELECT_SQL + "WHERE id = ?",
            (entry_id,),
        )
        return KnowledgeEntry(**dict(rows[0])) if rows else None

    async def mark_vector_sync_status(
        self,
        entry_id: int,
        *,
        status: str,
        error_message: str = "",
        synced_at: str = "",
        retry_increment: bool = False,
    ) -> str:
        """更新向量同步状态。"""
        cursor = await self._db.execute(
            "UPDATE knowledge_base SET "
            "vector_sync_status = ?, "
            "vector_synced_at = ?, "
            "vector_sync_error = ?, "
            "vector_sync_retry_count = vector_sync_retry_count + ?, "
            "updated_at = datetime('now') "
            "WHERE id = ?",
            (
                status,
                synced_at,
                error_message,
                1 if retry_increment else 0,
                entry_id,
            ),
        )
        await self._db.commit()
        return WriteResult.APPLIED if cursor.rowcount else WriteResult.SKIPPED

    async def insert_entry(
        self,
        *,
        category: str,
        title: str,
        content: str,
        keywords: str,
        priority: int,
        sync_source: str,
        sync_ref: str = "",
        content_type: str = "faq",
        content_origin: str = "seed_knowledge",
        created_by: str = "",
        updated_by: str = "",
        suggested_category: str = "",
        suggest_reason: str = "",
        vector_sync_status: str = VectorSyncStatus.SUCCESS,
        vector_synced_at: str = "",
        audience: str = KnowledgeAudience.ALL.value,
        review_status: str = KnowledgeReviewStatus.PUBLISHED.value,
        valid_from: str = "",
        valid_until: str = "",
        reviewed_by: str = "",
        reviewed_at: str = "",
    ) -> int:
        """插入一条非商品知识记录。"""
        cursor = await self._db.execute(
            KNOWLEDGE_INSERT_SQL,
            _build_insert_entry_params(locals()),
        )
        await self._db.commit()
        return int(cursor.lastrowid)

    async def get_pending_sync_entries(self, limit: int = 500) -> list[KnowledgeEntry]:
        """获取非商品类待同步知识条目。商品向量由商品状态机独立负责。"""
        rows = await self._db.execute_fetchall(
            ENTRY_SELECT_SQL
            + "WHERE category != ? AND vector_sync_status IN ('pending', 'failed') "
            "ORDER BY updated_at ASC LIMIT ?",
            ("product", limit),
        )
        return [KnowledgeEntry(**dict(row)) for row in rows]

    async def insert_retrieval_log(
        self,
        log_entry: KnowledgeRetrievalLogCreate,
    ) -> int:
        """写入一次知识检索命中日志。"""
        cursor = await self._db.execute(
            RETRIEVAL_LOG_INSERT_SQL,
            (
                log_entry.bot_type,
                log_entry.audience,
                "",
                log_entry.query_hash,
                log_entry.query_category,
                log_entry.retrieval_mode,
                json.dumps(log_entry.matched_entry_ids, ensure_ascii=False),
                json.dumps(log_entry.matched_titles, ensure_ascii=False),
                log_entry.result_count,
                log_entry.fallback_reason,
            ),
        )
        await self._db.commit()
        return int(cursor.lastrowid)

    async def list_recent_retrieval_logs(
        self,
        limit: int = 20,
    ) -> list[KnowledgeRetrievalLog]:
        """按时间倒序返回最近知识检索命中日志。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + RETRIEVAL_LOG_COLUMNS + " FROM knowledge_retrieval_logs "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [KnowledgeRetrievalLog(**dict(row)) for row in rows]


def _build_governance_filter(audience: str) -> tuple[str, tuple[object, ...]]:
    """构造已发布、有效期内、目标 audience 可见的过滤条件。"""
    if audience in {
        KnowledgeAudience.CUSTOMER.value,
        KnowledgeAudience.EMPLOYEE.value,
    }:
        return (
            PUBLISHED_KNOWLEDGE_FILTER_SQL + "AND audience IN (?, ?)",
            (
                KnowledgeReviewStatus.PUBLISHED.value,
                KnowledgeAudience.ALL.value,
                audience,
            ),
        )
    return (
        PUBLISHED_KNOWLEDGE_FILTER_SQL + "AND audience = ?",
        (KnowledgeReviewStatus.PUBLISHED.value, KnowledgeAudience.ALL.value),
    )


def _build_insert_entry_params(values: dict[str, object]) -> tuple[object, ...]:
    return (
        values["category"],
        values["content_type"],
        values["title"],
        values["content"],
        values["keywords"],
        values["priority"],
        values["sync_source"],
        values["sync_ref"],
        values["content_origin"],
        values["created_by"],
        values["updated_by"],
        values["suggested_category"],
        values["suggest_reason"],
        values["vector_sync_status"],
        values["vector_synced_at"],
        values["audience"],
        values["review_status"],
        values["valid_from"],
        values["valid_until"],
        values["reviewed_by"],
        values["reviewed_at"],
    )
