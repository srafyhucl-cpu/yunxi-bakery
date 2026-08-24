"""订单创建服务。"""

import json
from datetime import datetime
from uuid import uuid4

from app.constants.storefront import STOREFRONT_CHANNEL, STOREFRONT_DEMO_USER_ID
from app.models.order import Order, OrderStatus
from app.models.session import SessionCreate
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.service.order.inventory import NormalizedOrderItem, OrderInventoryService
from app.service.order.payment_runtime import build_initial_payment
from app.service.order.schedule import OrderScheduleService
from app.service.order.timeline import OrderTimelineService

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
ORDER_ID_PREFIX = "mp"


class OrderCreationService:
    """负责小程序订单创建链路。"""

    def __init__(
        self,
        order_repo: OrderRepo,
        session_repo: SessionRepo,
        inventory_service: OrderInventoryService,
        schedule_service: OrderScheduleService,
        timeline_service: OrderTimelineService,
    ) -> None:
        self._order_repo = order_repo
        self._session_repo = session_repo
        self._inventory_service = inventory_service
        self._schedule_service = schedule_service
        self._timeline_service = timeline_service

    async def create_order(
        self,
        payload: dict,
        *,
        user_id: str = STOREFRONT_DEMO_USER_ID,
    ) -> dict:
        """创建小程序订单草稿。"""
        order_items = await self._inventory_service.normalize_items(
            payload.get("items", [])
        )
        if not order_items:
            raise ValueError("订单商品不能为空")
        delivery = await self._schedule_service.build_delivery(payload)
        await self._inventory_service.reserve_inventory(order_items)
        order = await self._build_order(
            order_items,
            delivery=delivery,
            payload=payload,
            user_id=user_id,
        )
        await self._order_repo.create_order(order)
        await self._timeline_service.record_event(
            order_id=order.id,
            status=OrderStatus.PENDING.value,
            operator=f"miniapp:{user_id}",
            note="用户提交订单",
            created_at=order.created_at,
        )
        return {
            "orderId": order.id,
            "status": OrderStatus.PENDING.value,
            "totalFen": self._total_fen(order_items),
        }

    async def _build_order(
        self,
        order_items: list[NormalizedOrderItem],
        *,
        delivery: dict,
        payload: dict,
        user_id: str,
    ) -> Order:
        session = await self._session_repo.get_or_create(
            SessionCreate(id="", channel=STOREFRONT_CHANNEL, user_id=user_id)
        )
        now = datetime.now().strftime(TIME_FORMAT)
        return Order(
            id=self._build_order_id(),
            session_id=session.id,
            channel=STOREFRONT_CHANNEL,
            user_id=user_id,
            products=json.dumps(
                [item.__dict__ for item in order_items], ensure_ascii=False
            ),
            total_amount=self._total_fen(order_items) / 100,
            delivery=json.dumps(delivery, ensure_ascii=False),
            payment=json.dumps(build_initial_payment(now), ensure_ascii=False),
            status=OrderStatus.PENDING,
            remark=str(payload.get("remark", "")).strip(),
            created_at=now,
            updated_at=now,
        )

    def _build_order_id(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"{ORDER_ID_PREFIX}_{timestamp}_{uuid4().hex[:8]}"

    def _total_fen(self, order_items: list[NormalizedOrderItem]) -> int:
        return sum(item.price_fen * item.quantity for item in order_items)


__all__ = ["OrderCreationService"]
