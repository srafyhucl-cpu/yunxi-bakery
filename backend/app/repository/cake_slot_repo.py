"""定制蛋糕时段容量预占数据访问仓库。"""

from app.repository.base import BaseRepository

# 显式字段列表，避免 SELECT *。
_RESERVATION_COLUMNS = "order_id, slot_key, created_at"
_CAPACITY_COLUMNS = "slot_key, reserved_count, updated_at"

# 北京时间墙钟时间戳，与预约时段使用同一时区口径。
_BEIJING_NOW_SQL = "datetime('now', '+8 hours')"


class CakeSlotRepo(BaseRepository):
    """按 2 小时时段原子管理定制蛋糕预占量。"""

    async def reserve(self, slot_key: str, order_id: str, capacity: int) -> bool:
        """原子预占一个时段名额；同订单同时段幂等，超出容量返回 False。"""
        existing = await self.get_reservation(order_id)
        if existing is not None:
            return str(existing["slot_key"]) == slot_key

        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO cake_slot_reservations "
            "(order_id, slot_key, created_at) VALUES (?, ?, " + _BEIJING_NOW_SQL + ")",
            (order_id, slot_key),
        )
        if cursor.rowcount != 1:
            # 并发下同一订单已被另一个请求写入，只有同一时段才算幂等成功。
            current = await self.get_reservation(order_id)
            if current is not None and str(current["slot_key"]) == slot_key:
                return True
            return False

        capacity_cursor = await self._db.execute(
            "INSERT INTO cake_slot_capacity (slot_key, reserved_count, updated_at) "
            "VALUES (?, 1, " + _BEIJING_NOW_SQL + ") "
            "ON CONFLICT(slot_key) DO UPDATE SET "
            "reserved_count = reserved_count + 1, "
            "updated_at = " + _BEIJING_NOW_SQL + " "
            "WHERE reserved_count < ?",
            (slot_key, capacity),
        )
        if capacity_cursor.rowcount != 1:
            # 容量已满：撤销本次刚写入的预占，保证失败不占用名额。
            await self._db.execute(
                "DELETE FROM cake_slot_reservations "
                "WHERE order_id = ? AND slot_key = ?",
                (order_id, slot_key),
            )
            return False
        return True

    async def release(self, order_id: str) -> bool:
        """释放订单预占的名额；订单没有预占时幂等返回 True。"""
        existing = await self.get_reservation(order_id)
        if existing is None:
            return True

        slot_key = str(existing["slot_key"])
        cursor = await self._db.execute(
            "DELETE FROM cake_slot_reservations WHERE order_id = ?",
            (order_id,),
        )
        if cursor.rowcount != 1:
            # 并发释放已被其他请求完成，不得重复递减容量。
            return True

        await self._db.execute(
            "UPDATE cake_slot_capacity SET "
            "reserved_count = MAX(0, reserved_count - 1), "
            "updated_at = " + _BEIJING_NOW_SQL + " "
            "WHERE slot_key = ?",
            (slot_key,),
        )
        return True

    async def count_for_slot(self, slot_key: str) -> int:
        """读取指定时段当前已预占单量。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + _CAPACITY_COLUMNS + " FROM cake_slot_capacity "
            "WHERE slot_key = ? LIMIT 1",
            (slot_key,),
        )
        return int(rows[0]["reserved_count"]) if rows else 0

    async def get_reservation(self, order_id: str) -> dict | None:
        """读取订单当前预占记录。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + _RESERVATION_COLUMNS + " FROM cake_slot_reservations "
            "WHERE order_id = ? LIMIT 1",
            (order_id,),
        )
        return dict(rows[0]) if rows else None


__all__ = ["CakeSlotRepo"]
