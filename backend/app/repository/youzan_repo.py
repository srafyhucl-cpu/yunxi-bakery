"""有赞商品数据访问层。"""

import json

from app.models.content_change_history import WriteResult
from app.repository.base import BaseRepository
from app.repository.youzan_order_repo import YouzanOrderRepo  # noqa: F401


class YouzanProductRepo(BaseRepository):
    """有赞商品与库存大宽表仓库。"""

    async def get_by_id(self, item_id: int) -> dict | None:
        """根据商品唯一 ID 获取商品数据。"""
        rows = await self._db.execute_fetchall(
            "SELECT item_id, title, alias, price_fen, stock, image, is_active, "
            "skus_json, item_props_json, desc, tags, tag_ids_json, "
            "classification_ids_json, group_ids_json, second_group_ids_json, leaf_category_ids_json, "
            "last_sync_source, last_sync_ref, updated_at "
            "FROM youzan_products WHERE item_id = ?",
            (item_id,),
        )
        return dict(rows[0]) if rows else None

    async def get_by_alias(self, alias: str) -> dict | None:
        """根据有赞商品别名获取商品数据。"""
        rows = await self._db.execute_fetchall(
            "SELECT item_id, title, alias, price_fen, stock, image, is_active, "
            "skus_json, item_props_json, desc, tags, tag_ids_json, "
            "classification_ids_json, group_ids_json, second_group_ids_json, leaf_category_ids_json, "
            "last_sync_source, last_sync_ref, updated_at "
            "FROM youzan_products WHERE alias = ?",
            (alias,),
        )
        return dict(rows[0]) if rows else None

    async def list_current_products(
        self,
        *,
        keyword: str = "",
        is_active: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """分页获取当前商品宽表内容。"""
        clauses = ["1 = 1"]
        params: list[object] = []
        if keyword:
            like = f"%{keyword}%"
            clauses.append("(title LIKE ? OR alias LIKE ? OR tags LIKE ?)")
            params.extend([like, like, like])
        if is_active in {"0", "1"}:
            clauses.append("is_active = ?")
            params.append(int(is_active))
        rows = await self._db.execute_fetchall(
            "SELECT item_id, title, alias, price_fen, stock, image, is_active, "
            "skus_json, item_props_json, desc, tags, tag_ids_json, "
            "classification_ids_json, group_ids_json, second_group_ids_json, leaf_category_ids_json "
            "FROM youzan_products "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY updated_at DESC, item_id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return [dict(row) for row in rows]

    async def list_public_categories(self) -> list[dict]:
        """返回有赞商品分组，按分组排序和名称稳定输出。"""
        rows = await self._db.execute_fetchall(
            "SELECT tag_id, title, sort, product_count "
            "FROM youzan_product_categories "
            "WHERE product_count > 0 AND is_public = 1 "
            "ORDER BY sort ASC, title ASC, tag_id ASC"
        )
        return [dict(row) for row in rows]

    async def upsert_category(
        self,
        *,
        tag_id: str,
        title: str,
        sort: int = 0,
        product_count: int = 0,
        is_public: int = 1,
    ) -> None:
        """写入或更新有赞商品分组映射。"""
        await self._db.execute(
            "INSERT INTO youzan_product_categories (tag_id, title, sort, product_count, is_public, updated_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(tag_id) DO UPDATE SET "
            "title = excluded.title, "
            "sort = excluded.sort, "
            "product_count = excluded.product_count, "
            "is_public = excluded.is_public, "
            "updated_at = excluded.updated_at",
            (tag_id, title, sort, product_count, is_public),
        )
        await self._db.commit()

    async def get_category(self, tag_id: str) -> dict | None:
        """按有赞 tag id 读取分组映射。"""
        rows = await self._db.execute_fetchall(
            "SELECT tag_id, title, sort, product_count, is_public "
            "FROM youzan_product_categories WHERE tag_id = ?",
            (tag_id,),
        )
        return dict(rows[0]) if rows else None

    async def list_products_by_category_tag(
        self,
        tag_id: str,
        *,
        limit: int = 50,
    ) -> list[dict]:
        """按有赞 tag id 精确查询在售商品宽表。"""
        like = f'%"{tag_id}"%'
        rows = await self._db.execute_fetchall(
            "SELECT item_id, title, alias, price_fen, stock, image, is_active, "
            "skus_json, item_props_json, desc, tags, tag_ids_json, "
            "classification_ids_json, group_ids_json, second_group_ids_json, leaf_category_ids_json "
            "FROM youzan_products "
            "WHERE is_active = 1 AND tag_ids_json LIKE ? "
            "ORDER BY updated_at DESC, item_id DESC LIMIT ?",
            (like, limit),
        )
        return [dict(row) for row in rows]

    async def list_products_by_category_key(
        self,
        category_key: str,
        *,
        limit: int = 50,
    ) -> list[dict]:
        """按稳定分类 key 查询在售商品宽表。"""
        column = "tag_ids_json"
        raw_id = category_key
        prefixes = {
            "tag-": "tag_ids_json",
            "classification-": "classification_ids_json",
            "group-": "group_ids_json",
            "second-group-": "second_group_ids_json",
            "leaf-category-": "leaf_category_ids_json",
        }
        for prefix, candidate_column in prefixes.items():
            if category_key.startswith(prefix):
                column = candidate_column
                raw_id = category_key.replace(prefix, "", 1)
                break
        like = f'%"{raw_id}"%'
        rows = await self._db.execute_fetchall(
            "SELECT item_id, title, alias, price_fen, stock, image, is_active, "
            "skus_json, item_props_json, desc, tags, tag_ids_json, "
            "classification_ids_json, group_ids_json, second_group_ids_json, leaf_category_ids_json "
            "FROM youzan_products WHERE is_active = 1 AND "
            + column
            + " LIKE ? ORDER BY updated_at DESC, item_id DESC LIMIT ?",
            (like, limit),
        )
        return [dict(row) for row in rows]

    async def count_current_products(
        self, *, keyword: str = "", is_active: str = ""
    ) -> int:
        """返回当前商品宽表筛选后的总数。"""
        clauses = ["1 = 1"]
        params: list[object] = []
        if keyword:
            like = f"%{keyword}%"
            clauses.append("(title LIKE ? OR alias LIKE ? OR tags LIKE ?)")
            params.extend([like, like, like])
        if is_active in {"0", "1"}:
            clauses.append("is_active = ?")
            params.append(int(is_active))
        where_sql = " AND ".join(clauses)
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) AS c FROM youzan_products WHERE " + where_sql,
            tuple(params),
        )
        return int(rows[0]["c"]) if rows else 0

    async def upsert_product(
        self,
        item_id: int,
        title: str,
        alias: str,
        price_fen: int,
        stock: int,
        image: str,
        is_active: int,
        updated_at: str,
        skus_json: str = "[]",
        item_props_json: str = "[]",
        desc: str = "",
        tags: str = "",
        tag_ids_json: str = "[]",
        classification_ids_json: str = "[]",
        group_ids_json: str = "[]",
        second_group_ids_json: str = "[]",
        leaf_category_ids_json: str = "[]",
        sold_num: int = 0,
        item_no: str = "",
        *,
        sync_source: str = "",
        sync_ref: str = "",
    ) -> str:
        """原子化 upsert 商品数据，并返回是否真实写入。"""
        try:
            cursor = await self._db.execute(
                "INSERT INTO youzan_products ("
                "item_id, title, alias, price_fen, stock, image, is_active, "
                "skus_json, item_props_json, desc, tags, tag_ids_json, "
                "classification_ids_json, group_ids_json, second_group_ids_json, leaf_category_ids_json, "
                "sold_num, item_no, "
                "last_sync_source, last_sync_ref, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(item_id) DO UPDATE SET "
                "title = excluded.title, "
                "alias = excluded.alias, "
                "price_fen = excluded.price_fen, "
                "stock = excluded.stock, "
                "image = excluded.image, "
                "is_active = excluded.is_active, "
                "skus_json = excluded.skus_json, "
                "item_props_json = excluded.item_props_json, "
                "desc = excluded.desc, "
                "tags = excluded.tags, "
                "tag_ids_json = excluded.tag_ids_json, "
                "classification_ids_json = excluded.classification_ids_json, "
                "group_ids_json = excluded.group_ids_json, "
                "second_group_ids_json = excluded.second_group_ids_json, "
                "leaf_category_ids_json = excluded.leaf_category_ids_json, "
                "sold_num = excluded.sold_num, "
                "item_no = excluded.item_no, "
                "last_sync_source = excluded.last_sync_source, "
                "last_sync_ref = excluded.last_sync_ref, "
                "updated_at = excluded.updated_at "
                "WHERE excluded.updated_at > youzan_products.updated_at",
                (
                    item_id,
                    title,
                    alias,
                    price_fen,
                    stock,
                    image,
                    is_active,
                    skus_json,
                    item_props_json,
                    desc,
                    tags,
                    tag_ids_json,
                    classification_ids_json,
                    group_ids_json,
                    second_group_ids_json,
                    leaf_category_ids_json,
                    sold_num,
                    item_no,
                    sync_source,
                    sync_ref,
                    updated_at,
                ),
            )
            await self._db.commit()
            return WriteResult.APPLIED if cursor.rowcount else WriteResult.SKIPPED
        except Exception:
            return WriteResult.FAILED

    async def list_active_item_ids(self) -> list[int]:
        """返回所有本地标记为在售（is_active=1）的商品 item_id 列表。"""
        rows = await self._db.execute_fetchall(
            "SELECT item_id FROM youzan_products WHERE is_active = 1"
        )
        return [int(row["item_id"]) for row in rows]

    async def list_all_item_ids(self) -> list[int]:
        """返回 youzan_products 全量 item_id（含下架），用于历史销量全量同步。"""
        rows = await self._db.execute_fetchall("SELECT item_id FROM youzan_products")
        return [int(row["item_id"]) for row in rows]

    async def delete_product(
        self,
        item_id: int,
        updated_at: str,
        *,
        sync_source: str = "",
        sync_ref: str = "",
    ) -> str:
        """根据有赞商品 ID 软下架商品，并记录最后修改来源。"""
        cursor = await self._db.execute(
            "UPDATE youzan_products SET is_active = 0, "
            "last_sync_source = CASE WHEN ? != '' THEN ? ELSE last_sync_source END, "
            "last_sync_ref = CASE WHEN ? != '' THEN ? ELSE last_sync_ref END, "
            "updated_at = ? WHERE item_id = ? AND ? > updated_at",
            (
                sync_source,
                sync_source,
                sync_ref,
                sync_ref,
                updated_at,
                item_id,
                updated_at,
            ),
        )
        await self._db.commit()
        return WriteResult.APPLIED if cursor.rowcount else WriteResult.SKIPPED

    async def get_prices_and_stocks(self, item_ids: list[str]) -> dict[str, dict]:
        """批量查询商品单价（分）、库存、上下架和销量，并获取商品编码。"""
        valid_ids = [int(i) for i in item_ids if i and i.isdigit()]
        if not valid_ids:
            return {}
        placeholders = ",".join("?" * len(valid_ids))
        rows = await self._db.execute_fetchall(
            "SELECT yp.item_id, yp.price_fen, yp.stock, yp.is_active, yp.item_no, "
            "COALESCE(agg.total_sold, yp.sold_num) AS sold_num "
            "FROM youzan_products yp "
            "LEFT JOIN ("
            "SELECT item_no, SUM(sold_num) AS total_sold "
            "FROM youzan_products "
            "WHERE item_no IS NOT NULL AND item_no != '' "
            "GROUP BY item_no"
            ") agg ON yp.item_no = agg.item_no AND yp.item_no != '' "
            "WHERE yp.item_id IN (" + placeholders + ")",
            tuple(valid_ids),
        )
        return {
            str(row["item_id"]): {
                "price_fen": row["price_fen"],
                "stock": row["stock"],
                "is_active": row["is_active"],
                "sold_num": row["sold_num"] or 0,
                "item_no": row["item_no"] or "",
            }
            for row in rows
        }

    async def bulk_update_sold_num(self, sold_num_map: dict[int, int]) -> int:
        """批量更新在售商品销量，返回实际更新行数。"""
        if not sold_num_map:
            return 0
        count = 0
        for item_id, sold_num in sold_num_map.items():
            cursor = await self._db.execute(
                "UPDATE youzan_products SET sold_num = ? WHERE item_id = ?",
                (sold_num, item_id),
            )
            count += cursor.rowcount
        await self._db.commit()
        return count

    async def bulk_update_sold_and_no(
        self, update_map: dict[int, tuple[int, str]]
    ) -> int:
        """批量更新商品销量与 item_no，返回实际更新行数。"""
        if not update_map:
            return 0
        count = 0
        for item_id, (sold_num, item_no) in update_map.items():
            cursor = await self._db.execute(
                "UPDATE youzan_products SET sold_num = ?, item_no = ? WHERE item_id = ?",
                (sold_num, item_no, item_id),
            )
            count += cursor.rowcount
        await self._db.commit()
        return count

    async def bulk_update_item_base_categories(
        self,
        category_map: dict[int, dict[str, list[str]]],
    ) -> int:
        """批量更新 ITEM_INFO 返回的商品分类与分组 ID。"""
        if not category_map:
            return 0
        count = 0
        for item_id, categories in category_map.items():
            cursor = await self._db.execute(
                "UPDATE youzan_products SET "
                "classification_ids_json = ?, "
                "group_ids_json = ?, "
                "second_group_ids_json = ?, "
                "leaf_category_ids_json = ? "
                "WHERE item_id = ?",
                (
                    json.dumps(
                        categories.get("classification_ids", []), ensure_ascii=False
                    ),
                    json.dumps(categories.get("group_ids", []), ensure_ascii=False),
                    json.dumps(
                        categories.get("second_group_ids", []), ensure_ascii=False
                    ),
                    json.dumps(
                        categories.get("leaf_category_ids", []), ensure_ascii=False
                    ),
                    item_id,
                ),
            )
            count += cursor.rowcount
        await self._db.commit()
        return count

    async def bulk_update_tag_ids(self, tag_ids_map: dict[int, list[str]]) -> int:
        """批量更新商品所属有赞分组 tag id。"""
        if not tag_ids_map:
            return 0
        count = 0
        for item_id, tag_ids in tag_ids_map.items():
            cursor = await self._db.execute(
                "UPDATE youzan_products SET tag_ids_json = ? WHERE item_id = ?",
                (json.dumps(tag_ids, ensure_ascii=False), item_id),
            )
            count += cursor.rowcount
        await self._db.commit()
        return count
