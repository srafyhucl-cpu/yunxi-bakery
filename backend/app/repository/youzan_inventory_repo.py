"""有赞商品库存写入仓库。"""

from app.repository.base import BaseRepository


class YouzanInventoryRepo(BaseRepository):
    """封装小程序订单所需的商品库存预占与释放。"""

    async def reserve_stock(self, item_id: str, quantity: int) -> bool:
        """库存足够且商品在售时扣减库存。"""
        if quantity <= 0 or not item_id.isdigit():
            return False
        cursor = await self._db.execute(
            "UPDATE youzan_products "
            "SET stock = stock - ? "
            "WHERE item_id = ? AND is_active = 1 AND stock >= ?",
            (quantity, int(item_id), quantity),
        )
        return bool(cursor.rowcount == 1)

    async def release_stock(self, item_id: str, quantity: int) -> bool:
        """释放已预占库存。"""
        if quantity <= 0 or not item_id.isdigit():
            return False
        cursor = await self._db.execute(
            "UPDATE youzan_products SET stock = stock + ? WHERE item_id = ?",
            (quantity, int(item_id)),
        )
        return bool(cursor.rowcount == 1)
