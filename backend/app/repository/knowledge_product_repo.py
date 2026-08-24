"""知识库商品知识数据访问层。

职责：商品知识条目的 upsert、软下架和管理后台分页查询。
"""

from app.models.content_change_history import WriteResult
from app.models.knowledge import VectorSyncStatus
from app.repository.base import BaseRepository

PRODUCT_CATEGORY = "product"
VECTOR_SYNC_ERROR_MAX_LENGTH = 500


class KnowledgeProductRepo(BaseRepository):
    """商品知识仓库：负责商品类知识的写操作和管理后台查询。"""

    @staticmethod
    def _build_product_where(
        search: str,
        is_active: int | None,
        sync_source: str,
        vector_sync_status: str,
        featured_titles: list[str] | None,
        youzan_item_id_filter: str,
        keyword_filter: str,
        item_no_filter: str = "",
    ) -> tuple[list[str], list] | None:
        """构建商品筛选 WHERE 子句与参数列表；每个字段显式加上 kb. 前缀防止联合查询中字段歧义。"""
        keyword = f"%{search}%"
        clauses: list[str] = [
            "kb.category = 'product'",
            "(kb.title LIKE ? OR kb.content LIKE ? OR kb.keywords LIKE ?)",
        ]
        params: list = [keyword, keyword, keyword]
        if is_active is not None:
            clauses.append("kb.is_active = ?")
            params.append(is_active)
        if sync_source:
            clauses.append("kb.last_sync_source = ?")
            params.append(sync_source)
        if vector_sync_status:
            clauses.append("kb.vector_sync_status = ?")
            params.append(vector_sync_status)
        if featured_titles is not None:
            if not featured_titles:
                return None
            placeholders = ",".join("?" * len(featured_titles))
            clauses.append("kb.title IN (" + placeholders + ")")
            params.extend(featured_titles)
        if youzan_item_id_filter:
            clauses.append("kb.youzan_item_id = ?")
            params.append(youzan_item_id_filter)
        if item_no_filter:
            clauses.append(
                "kb.youzan_item_id IN (SELECT CAST(item_id AS TEXT) FROM youzan_products WHERE item_no LIKE ?)"
            )
            params.append(f"%{item_no_filter}%")
        if keyword_filter:
            clauses.append("kb.keywords LIKE ?")
            params.append(f"%{keyword_filter}%")
        return clauses, params

    @staticmethod
    def _build_sort_order(sort_by: str, sort_order: str) -> str:
        """根据传入的排序参数构建 ORDER BY 子句。"""
        SORT_FIELD_MAP = {
            "title": "kb.title",
            "priority": "kb.priority",
            "is_active": "kb.is_active",
            "vector_sync_status": "kb.vector_sync_status",
            "updated_at": "kb.updated_at",
            "priceFen": "yp.price_fen",
            "stock": "yp.stock",
            "soldNum": "agg_sold_num",
            "itemNo": "yp.item_no",
        }
        db_sort_field = SORT_FIELD_MAP.get(sort_by)
        db_sort_order = "ASC" if sort_order.lower() == "asc" else "DESC"

        if db_sort_field:
            return f"ORDER BY {db_sort_field} {db_sort_order}, kb.updated_at DESC, kb.priority DESC"
        return "ORDER BY kb.updated_at DESC, kb.priority DESC"

    @staticmethod
    def _row_to_product_entry(row: dict, entry_class) -> object:
        """将联合查询出的单行数据转换为带动态挂载字段的 KnowledgeEntry。"""
        row_dict = dict(row)
        price_fen = row_dict.pop("price_fen", None)
        stock = row_dict.pop("stock", None)
        sold_num = row_dict.pop("agg_sold_num", 0)
        item_no = row_dict.pop("item_no", "")
        image_url = row_dict.pop("image_url", "")
        tag_ids_json = row_dict.pop("tag_ids_json", "[]")
        classification_ids_json = row_dict.pop("classification_ids_json", "[]")
        group_ids_json = row_dict.pop("group_ids_json", "[]")
        second_group_ids_json = row_dict.pop("second_group_ids_json", "[]")
        leaf_category_ids_json = row_dict.pop("leaf_category_ids_json", "[]")

        entry = entry_class(**row_dict)
        setattr(entry, "price_fen", price_fen)
        setattr(entry, "stock", stock)
        setattr(entry, "sold_num", sold_num)
        setattr(entry, "item_no", item_no)
        setattr(entry, "image_url", image_url)
        setattr(entry, "tag_ids_json", tag_ids_json)
        setattr(entry, "classification_ids_json", classification_ids_json)
        setattr(entry, "group_ids_json", group_ids_json)
        setattr(entry, "second_group_ids_json", second_group_ids_json)
        setattr(entry, "leaf_category_ids_json", leaf_category_ids_json)
        return entry

    async def get_all_products(
        self,
        search: str = "",
        limit: int = 50,
        offset: int = 0,
        is_active: int | None = None,
        sync_source: str = "",
        vector_sync_status: str = "",
        featured_titles: list[str] | None = None,
        youzan_item_id_filter: str = "",
        keyword_filter: str = "",
        item_no_filter: str = "",
        sort_by: str = "",
        sort_order: str = "desc",
    ) -> list:
        """分页获取商品知识，支持多维度过滤，并通过与 youzan_products 做 LEFT JOIN 聚合实现安全的同款销量合并排序。"""
        from app.models.knowledge import KnowledgeEntry

        result = self._build_product_where(
            search,
            is_active,
            sync_source,
            vector_sync_status,
            featured_titles,
            youzan_item_id_filter,
            keyword_filter,
            item_no_filter,
        )
        if result is None:
            return []
        clauses, params = result
        where = " AND ".join(clauses)
        order_clause = self._build_sort_order(sort_by, sort_order)

        sql = (
            "SELECT "
            "kb.id, kb.category, kb.content_type, kb.title, kb.content, kb.keywords, kb.priority, "
            "kb.is_active, kb.youzan_item_id, kb.last_sync_source, kb.last_sync_ref, "
            "kb.vector_sync_status, kb.updated_at, "
            "yp.price_fen, yp.stock, COALESCE(agg.total_sold, yp.sold_num) AS agg_sold_num, "
            "yp.item_no, yp.image AS image_url, yp.tag_ids_json, "
            "yp.classification_ids_json, yp.group_ids_json, "
            "yp.second_group_ids_json, yp.leaf_category_ids_json "
            "FROM knowledge_base kb "
            "LEFT JOIN youzan_products yp ON kb.youzan_item_id = CAST(yp.item_id AS TEXT) "
            "LEFT JOIN ("
            "    SELECT item_no, SUM(sold_num) AS total_sold "
            "    FROM youzan_products "
            "    WHERE item_no IS NOT NULL AND item_no != '' "
            "    GROUP BY item_no"
            ") agg ON yp.item_no = agg.item_no AND yp.item_no != '' "
            f"WHERE {where} {order_clause} LIMIT ? OFFSET ?"
        )

        params.extend([limit, offset])
        rows = await self._db.execute_fetchall(sql, tuple(params))
        return [self._row_to_product_entry(r, KnowledgeEntry) for r in rows]

    async def count_products(
        self,
        search: str = "",
        is_active: int | None = None,
        sync_source: str = "",
        vector_sync_status: str = "",
        featured_titles: list[str] | None = None,
        youzan_item_id_filter: str = "",
        keyword_filter: str = "",
        item_no_filter: str = "",
    ) -> int:
        """返回商品类知识条目总数，显式加上 kb 前缀支持联合过滤。"""
        result = self._build_product_where(
            search,
            is_active,
            sync_source,
            vector_sync_status,
            featured_titles,
            youzan_item_id_filter,
            keyword_filter,
            item_no_filter,
        )
        if result is None:
            return 0
        clauses, params = result
        where = " AND ".join(clauses)
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) AS c FROM knowledge_base kb WHERE " + where,
            tuple(params),
        )
        return int(rows[0]["c"]) if rows else 0

    async def upsert_product_knowledge(
        self,
        youzan_item_id: str,
        title: str,
        content: str,
        keywords: str,
        priority: int,
        updated_at: str,
        *,
        sync_source: str = "",
        sync_ref: str = "",
    ) -> str:
        """原子 upsert 商品知识，并返回是否真实写入。"""
        try:
            cursor = await self._db.execute(
                "INSERT INTO knowledge_base ("
                "category, content_type, title, content, keywords, priority, youzan_item_id, "
                "is_active, last_sync_source, last_sync_ref, content_origin, "
                "vector_sync_status, vector_synced_at, vector_sync_error, "
                "vector_sync_retry_count, updated_at"
                ") VALUES ('product', 'product', ?, ?, ?, ?, ?, 1, ?, ?, "
                "'youzan_runtime', 'pending', '', '', 0, ?) "
                "ON CONFLICT(youzan_item_id) DO UPDATE SET "
                "title = excluded.title, "
                "content = excluded.content, "
                "keywords = excluded.keywords, "
                "priority = excluded.priority, "
                "is_active = 1, "
                "last_sync_source = excluded.last_sync_source, "
                "last_sync_ref = excluded.last_sync_ref, "
                "content_type = excluded.content_type, "
                "content_origin = excluded.content_origin, "
                "vector_sync_status = excluded.vector_sync_status, "
                "vector_synced_at = excluded.vector_synced_at, "
                "vector_sync_error = '', "
                "vector_sync_retry_count = 0, "
                "updated_at = excluded.updated_at "
                "WHERE excluded.updated_at > knowledge_base.updated_at",
                (
                    title,
                    content,
                    keywords,
                    priority,
                    youzan_item_id,
                    sync_source,
                    sync_ref,
                    updated_at,
                ),
            )
            await self._db.commit()
            return WriteResult.APPLIED if cursor.rowcount else WriteResult.SKIPPED
        except Exception as exc:
            from app.logger import setup_logger

            setup_logger().error(
                "商品知识 upsert 失败 item_id=%s err=%s",
                youzan_item_id,
                exc,
            )
            return WriteResult.FAILED

    async def get_product_vector_revision(self, youzan_item_id: str) -> str | None:
        """读取商品知识当前内容 revision。"""
        rows = await self._db.execute_fetchall(
            "SELECT updated_at FROM knowledge_base "
            "WHERE category = ? AND youzan_item_id = ?",
            (PRODUCT_CATEGORY, youzan_item_id),
        )
        return str(rows[0]["updated_at"]) if rows else None

    async def claim_product_vector_sync(
        self,
        youzan_item_id: str,
        revision: str,
        *,
        stale_before: str | None = None,
    ) -> bool:
        """条件认领商品向量任务并写入租约时间。"""
        status_clause = (
            "vector_sync_status IN (?, ?) "
            "OR (vector_sync_status = ? AND vector_synced_at <= ?)"
        )
        parameters: tuple[object, ...] = (
            VectorSyncStatus.PENDING.value,
            VectorSyncStatus.FAILED.value,
            VectorSyncStatus.SYNCING.value,
            stale_before or "",
            youzan_item_id,
            revision,
        )
        if stale_before is None:
            status_clause = "vector_sync_status IN (?, ?)"
            parameters = (
                VectorSyncStatus.PENDING.value,
                VectorSyncStatus.FAILED.value,
                youzan_item_id,
                revision,
            )
        cursor = await self._db.execute(
            "UPDATE knowledge_base SET "
            "vector_sync_status = ?, vector_synced_at = datetime('now'), "
            "vector_sync_error = '' "
            "WHERE category = ? AND youzan_item_id = ? AND updated_at = ? "
            "AND (" + status_clause + ")",
            (
                VectorSyncStatus.SYNCING.value,
                PRODUCT_CATEGORY,
                *parameters[-2:],
                *parameters[:-2],
            ),
        )
        await self._db.commit()
        return bool(cursor.rowcount)

    async def mark_product_vector_sync_success(
        self,
        youzan_item_id: str,
        revision: str,
    ) -> bool:
        """在向量写入成功后条件标记商品向量状态。"""
        cursor = await self._db.execute(
            "UPDATE knowledge_base SET "
            "vector_sync_status = ?, vector_synced_at = datetime('now'), "
            "vector_sync_error = '' "
            "WHERE category = ? AND youzan_item_id = ? AND updated_at = ? "
            "AND vector_sync_status = ?",
            (
                VectorSyncStatus.SUCCESS.value,
                PRODUCT_CATEGORY,
                youzan_item_id,
                revision,
                VectorSyncStatus.SYNCING.value,
            ),
        )
        await self._db.commit()
        return bool(cursor.rowcount)

    async def mark_product_vector_sync_failed(
        self,
        youzan_item_id: str,
        revision: str,
        error: str,
    ) -> bool:
        """条件记录商品向量失败并原子增加重试次数。"""
        cursor = await self._db.execute(
            "UPDATE knowledge_base SET "
            "vector_sync_status = ?, vector_synced_at = '', "
            "vector_sync_error = substr(?, 1, ?), "
            "vector_sync_retry_count = vector_sync_retry_count + 1 "
            "WHERE category = ? AND youzan_item_id = ? AND updated_at = ? "
            "AND vector_sync_status = ?",
            (
                VectorSyncStatus.FAILED.value,
                error,
                VECTOR_SYNC_ERROR_MAX_LENGTH,
                PRODUCT_CATEGORY,
                youzan_item_id,
                revision,
                VectorSyncStatus.SYNCING.value,
            ),
        )
        await self._db.commit()
        return bool(cursor.rowcount)

    async def list_product_vector_sync_candidates(
        self,
        *,
        stale_before: str,
        limit: int = 100,
    ) -> list[dict]:
        """列出待同步、失败和过期租约的商品知识条目。"""
        rows = await self._db.execute_fetchall(
            "SELECT youzan_item_id, title, content, is_active, updated_at, "
            "vector_sync_status, vector_sync_retry_count, vector_synced_at "
            "FROM knowledge_base "
            "WHERE category = ? AND ("
            "vector_sync_status IN (?, ?) "
            "OR (vector_sync_status = ? AND vector_synced_at <= ?)"
            ") ORDER BY updated_at ASC LIMIT ?",
            (
                PRODUCT_CATEGORY,
                VectorSyncStatus.PENDING.value,
                VectorSyncStatus.FAILED.value,
                VectorSyncStatus.SYNCING.value,
                stale_before,
                limit,
            ),
        )
        return [dict(row) for row in rows]

    async def delete_product_knowledge(
        self,
        youzan_item_id: str,
        *,
        sync_source: str = "",
        sync_ref: str = "",
    ) -> str:
        """软下架商品知识，并记录最后修改来源。"""
        cursor = await self._db.execute(
            "UPDATE knowledge_base SET is_active = 0, "
            "last_sync_source = CASE WHEN ? != '' THEN ? ELSE last_sync_source END, "
            "last_sync_ref = CASE WHEN ? != '' THEN ? ELSE last_sync_ref END, "
            "vector_sync_status = 'pending', "
            "vector_synced_at = '', "
            "vector_sync_error = '', "
            "vector_sync_retry_count = 0, "
            "updated_at = datetime('now') "
            "WHERE category = ? AND youzan_item_id = ? AND is_active = 1",
            (
                sync_source,
                sync_source,
                sync_ref,
                sync_ref,
                PRODUCT_CATEGORY,
                youzan_item_id,
            ),
        )
        await self._db.commit()
        return WriteResult.APPLIED if cursor.rowcount else WriteResult.SKIPPED
