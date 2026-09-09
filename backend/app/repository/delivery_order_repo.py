"""配送单与回调事件仓储。"""

from app.models.delivery import DeliveryOrder, DeliveryOrderStatus
from app.repository.base import BaseRepository


class DeliveryOrderRepo(BaseRepository):
    """保存本地配送单状态和外部回调幂等记录。"""

    async def create(self, delivery_order: DeliveryOrder) -> None:
        await self._db.execute(
            "INSERT INTO delivery_orders ("
            "order_id, provider, provider_order_id, status, delivery_fee_fen, "
            "pickup_address, receiver_address, last_synced_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                delivery_order.order_id,
                delivery_order.provider,
                delivery_order.provider_order_id,
                delivery_order.status.value,
                delivery_order.delivery_fee_fen,
                delivery_order.pickup_address,
                delivery_order.receiver_address,
                delivery_order.last_synced_at,
            ),
        )

    async def get_by_order_id(self, order_id: str) -> DeliveryOrder | None:
        rows = await self._db.execute_fetchall(
            "SELECT order_id, provider, provider_order_id, status, delivery_fee_fen, "
            "pickup_address, receiver_address, last_synced_at FROM delivery_orders "
            "WHERE order_id = ? LIMIT 1",
            (order_id,),
        )
        if not rows:
            return None
        row = rows[0]
        return DeliveryOrder(
            order_id=str(row["order_id"]),
            provider=str(row["provider"]),
            provider_order_id=str(row["provider_order_id"]),
            status=DeliveryOrderStatus(str(row["status"])),
            delivery_fee_fen=(
                int(row["delivery_fee_fen"])
                if row["delivery_fee_fen"] is not None
                else None
            ),
            pickup_address=str(row["pickup_address"]),
            receiver_address=str(row["receiver_address"]),
            last_synced_at=str(row["last_synced_at"]),
        )

    async def update_status(
        self,
        order_id: str,
        status: DeliveryOrderStatus,
        last_synced_at: str,
    ) -> None:
        await self._db.execute(
            "UPDATE delivery_orders SET status = ?, last_synced_at = ? "
            "WHERE order_id = ?",
            (status.value, last_synced_at, order_id),
        )

    async def claim_event(self, event_id: str, provider: str, received_at: str) -> bool:
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO delivery_callback_events "
            "(event_id, provider, received_at, status) VALUES (?, ?, ?, ?)",
            (event_id, provider, received_at, "received"),
        )
        return bool(cursor.rowcount == 1)
