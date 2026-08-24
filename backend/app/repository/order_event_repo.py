"""小程序订单状态事件仓储。"""

from app.models.order import OrderEvent
from app.repository.base import BaseRepository


class OrderEventRepo(BaseRepository):
    """保存和查询订单状态事件。"""

    async def add(self, event: OrderEvent) -> int:
        cursor = await self._db.execute(
            "INSERT INTO order_events (order_id, status, operator, note, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                event.order_id,
                event.status,
                event.operator,
                event.note,
                event.created_at,
            ),
        )
        return int(cursor.lastrowid)

    async def list_by_order(self, order_id: str) -> list[OrderEvent]:
        rows = await self._db.execute_fetchall(
            "SELECT id, order_id, status, operator, note, created_at "
            "FROM order_events WHERE order_id = ? ORDER BY created_at ASC, id ASC",
            (order_id,),
        )
        return [OrderEvent(**dict(row)) for row in rows]
