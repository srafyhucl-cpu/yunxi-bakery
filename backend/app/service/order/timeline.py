"""订单事件时间线支撑服务。"""

from app.models.order import Order, OrderEvent
from app.repository.order_event_repo import OrderEventRepo
from app.service.order.serialization import OrderSerializationService


class OrderTimelineService:
    """负责订单事件记录与详情时间线序列化。"""

    def __init__(
        self,
        serialization_service: OrderSerializationService,
        event_repo: OrderEventRepo | None = None,
    ) -> None:
        self._serialization_service = serialization_service
        self._event_repo = event_repo

    async def serialize(self, order: Order) -> dict:
        """输出带时间线的订单展示模型。"""
        return self._serialization_service.serialize(
            order,
            events=await self.list_events(order.id),
        )

    async def record_event(
        self,
        *,
        order_id: str,
        status: str,
        operator: str,
        note: str,
        created_at: str,
    ) -> None:
        """追加订单状态事件。"""
        if self._event_repo is None:
            return
        await self._event_repo.add(
            OrderEvent(
                order_id=order_id,
                status=status,
                operator=operator,
                note=note,
                created_at=created_at,
            )
        )

    async def list_events(self, order_id: str) -> list[OrderEvent]:
        """读取订单事件时间线。"""
        if self._event_repo is None:
            return []
        return await self._event_repo.list_by_order(order_id)


__all__ = ["OrderTimelineService"]
