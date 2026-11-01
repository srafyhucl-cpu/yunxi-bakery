"""每日现烤库存数据访问仓库。"""

from app.repository.base import BaseRepository

# 与 product_daily_stock 表保持一致的显式字段列表，避免 SELECT *。
_DAILY_STOCK_COLUMNS = (
    "stock_date, product_id, total_qty, reserved_qty, "
    "updated_by, created_at, updated_at"
)

# 北京时间墙钟时间戳，库存按北京时间自然日切分。
_BEIJING_NOW_SQL = "datetime('now', '+8 hours')"


class ProductDailyStockRepo(BaseRepository):
    """按“日期 + 商品”管理日常现烤每日库存。"""

    async def get_for_date(self, product_id: str, stock_date: str) -> dict | None:
        """读取指定商品在某一天的每日库存记录。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + _DAILY_STOCK_COLUMNS + " FROM product_daily_stock "
            "WHERE stock_date = ? AND product_id = ? LIMIT 1",
            (stock_date, product_id),
        )
        return dict(rows[0]) if rows else None

    async def list_for_date(self, stock_date: str) -> list[dict]:
        """读取某一天的全部每日库存记录。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + _DAILY_STOCK_COLUMNS + " FROM product_daily_stock "
            "WHERE stock_date = ? ORDER BY product_id ASC",
            (stock_date,),
        )
        return [dict(row) for row in rows]

    async def list_products_with_stock(self, stock_date: str) -> list[dict]:
        """左连接商品宽表，返回在售商品与已有当日库存记录的历史商品。

        没有每日库存记录的在售商品也会返回（total_qty 归零），便于后台首次初始化。
        已下架但当天已有记录的商品同样保留，避免历史数据在页面消失。
        """
        rows = await self._db.execute_fetchall(
            "SELECT CAST(yp.item_id AS TEXT) AS product_id, yp.item_id, "
            "yp.title, yp.price_fen, yp.is_active, yp.stock AS youzan_stock, "
            "COALESCE(pds.total_qty, 0) AS total_qty, "
            "COALESCE(pds.reserved_qty, 0) AS reserved_qty, "
            "COALESCE(pds.total_qty, 0) - COALESCE(pds.reserved_qty, 0) "
            "AS available_qty, "
            "pds.updated_by, pds.updated_at, "
            "CASE WHEN pds.product_id IS NULL THEN 0 ELSE 1 END AS configured "
            "FROM youzan_products yp "
            "LEFT JOIN product_daily_stock pds "
            "ON pds.product_id = CAST(yp.item_id AS TEXT) "
            "AND pds.stock_date = ? "
            "WHERE yp.is_active = 1 OR pds.product_id IS NOT NULL "
            "ORDER BY yp.is_active DESC, yp.item_id ASC",
            (stock_date,),
        )
        return [dict(row) for row in rows]

    async def upsert_total(
        self,
        stock_date: str,
        product_id: str,
        total_qty: int,
        updated_by: str,
    ) -> bool:
        """原子写入当日总量；已预占数量高于新总量时拒绝更新。"""
        if total_qty < 0:
            return False
        cursor = await self._db.execute(
            "INSERT INTO product_daily_stock ("
            "stock_date, product_id, total_qty, reserved_qty, "
            "updated_by, created_at, updated_at"
            ") VALUES (?, ?, ?, 0, ?, "
            + _BEIJING_NOW_SQL
            + ", "
            + _BEIJING_NOW_SQL
            + ") "
            "ON CONFLICT(stock_date, product_id) DO UPDATE SET "
            "total_qty = excluded.total_qty, "
            "updated_by = excluded.updated_by, "
            "updated_at = excluded.updated_at "
            "WHERE product_daily_stock.reserved_qty <= excluded.total_qty",
            (stock_date, product_id, total_qty, updated_by),
        )
        return bool(cursor.rowcount == 1)

    async def copy_from_previous_date(self, target_date: str) -> int:
        """把之前最近一个有库存记录的日期复制到目标日期，只补缺失商品行。"""
        cursor = await self._db.execute(
            "INSERT INTO product_daily_stock ("
            "stock_date, product_id, total_qty, reserved_qty, "
            "updated_by, created_at, updated_at"
            ") SELECT ?, prev.product_id, prev.total_qty, 0, 'system_copy', "
            + _BEIJING_NOW_SQL
            + ", "
            + _BEIJING_NOW_SQL
            + " FROM product_daily_stock prev "
            "WHERE prev.stock_date = ("
            "SELECT MAX(stock_date) FROM product_daily_stock "
            "WHERE stock_date < ?"
            ") AND NOT EXISTS ("
            "SELECT 1 FROM product_daily_stock cur "
            "WHERE cur.stock_date = ? AND cur.product_id = prev.product_id"
            ")",
            (target_date, target_date, target_date),
        )
        return int(cursor.rowcount or 0)

    async def reserve(self, product_id: str, stock_date: str, quantity: int) -> bool:
        """原子预占每日库存，剩余可售量不足时失败。"""
        if quantity <= 0:
            return False
        cursor = await self._db.execute(
            "UPDATE product_daily_stock "
            "SET reserved_qty = reserved_qty + ?, updated_at = "
            + _BEIJING_NOW_SQL
            + " WHERE stock_date = ? AND product_id = ? "
            "AND total_qty - reserved_qty >= ?",
            (quantity, stock_date, product_id, quantity),
        )
        return bool(cursor.rowcount == 1)

    async def release(self, product_id: str, stock_date: str, quantity: int) -> bool:
        """原子释放每日库存预占，最低归零不产生负数。"""
        if quantity <= 0:
            return False
        cursor = await self._db.execute(
            "UPDATE product_daily_stock "
            "SET reserved_qty = MAX(0, reserved_qty - ?), updated_at = "
            + _BEIJING_NOW_SQL
            + " WHERE stock_date = ? AND product_id = ?",
            (quantity, stock_date, product_id),
        )
        return bool(cursor.rowcount == 1)


__all__ = ["ProductDailyStockRepo"]
