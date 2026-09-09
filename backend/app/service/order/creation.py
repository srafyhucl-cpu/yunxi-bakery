"""订单创建服务。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.constants.storefront import STOREFRONT_CHANNEL, STOREFRONT_DEMO_USER_ID
from app.models.delivery import DeliveryQuote
from app.models.order import Order, OrderStatus
from app.models.session import SessionCreate
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.service.order.inventory import NormalizedOrderItem, OrderInventoryService
from app.service.order.payment_runtime import build_initial_payment
from app.service.order.schedule import BEIJING_DELIVERY_TYPE, OrderScheduleService
from app.service.order.timeline import OrderTimelineService
from app.utils import fen_to_yuan_str

from app.service.delivery.provider import (
    DeliveryQuoteItem,
    DeliveryQuoteRequest,
    build_delivery_request_hash,
    normalize_delivery_quote_items,
)

if TYPE_CHECKING:
    from app.service.delivery.application import DeliveryApplicationService

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
        delivery_service: DeliveryApplicationService | None = None,
    ) -> None:
        self._order_repo = order_repo
        self._session_repo = session_repo
        self._inventory_service = inventory_service
        self._schedule_service = schedule_service
        self._timeline_service = timeline_service
        self._delivery_service = delivery_service

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
        goods_total_fen = self._goods_total_fen(order_items)
        delivery = await self._schedule_service.build_delivery(payload)
        payable_fen = await self._apply_delivery_quote(
            delivery,
            goods_total_fen=goods_total_fen,
            order_items=order_items,
            user_id=user_id,
        )
        await self._inventory_service.reserve_inventory(order_items)
        order = await self._build_order(
            order_items,
            delivery=delivery,
            payload=payload,
            user_id=user_id,
            payable_fen=payable_fen,
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
            "totalFen": payable_fen,
            "goodsTotalFen": goods_total_fen,
            "deliveryFeeFen": int(delivery["deliveryFeeFen"]),
            "payableFen": payable_fen,
        }

    async def _build_order(
        self,
        order_items: list[NormalizedOrderItem],
        *,
        delivery: dict,
        payload: dict,
        user_id: str,
        payable_fen: int,
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
            total_amount=float(fen_to_yuan_str(payable_fen)),
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

    async def _apply_delivery_quote(
        self,
        delivery: dict,
        *,
        goods_total_fen: int,
        order_items: list[NormalizedOrderItem],
        user_id: str,
    ) -> int:
        """把履约费用固化为订单金额快照。"""
        fulfillment_method = str(delivery.get("fulfillmentMethod", "pickup"))
        if fulfillment_method != BEIJING_DELIVERY_TYPE:
            delivery["deliveryFeeFen"] = 0
            delivery["goodsTotalFen"] = goods_total_fen
            delivery["payableFen"] = goods_total_fen
            return goods_total_fen
        quote_id = str(delivery.get("deliveryQuoteId", "")).strip()
        if not quote_id:
            raise ValueError("北京闪送订单必须先取得有效配送报价")
        if self._delivery_service is None:
            raise ValueError("配送报价服务未启用，不能提交闪送订单")
        quote = await self._delivery_service.require_payable_quote(
            quote_id,
            user_id,
            goods_total_fen,
        )
        self._validate_quote_request(
            delivery,
            quote,
            goods_total_fen=goods_total_fen,
            order_items=order_items,
        )
        delivery_fee_fen = quote.delivery_fee_fen
        if delivery_fee_fen is None:
            raise ValueError("配送报价尚未确认，不能支付")
        payable_fen = goods_total_fen + delivery_fee_fen
        delivery.update(
            {
                "deliveryFeeFen": delivery_fee_fen,
                "goodsTotalFen": goods_total_fen,
                "payableFen": payable_fen,
                "quoteTotalFen": quote.quote_total_fen,
                "quoteProvider": quote.provider,
            }
        )
        return payable_fen

    @staticmethod
    def _validate_quote_request(
        delivery: dict,
        quote: DeliveryQuote,
        *,
        goods_total_fen: int,
        order_items: list[NormalizedOrderItem],
    ) -> None:
        quote_request = DeliveryQuoteRequest(
            request_id=quote.quote_id,
            user_id=quote.user_id,
            pickup_address=str(delivery.get("pickupAddress", "")),
            receiver_name=str(delivery.get("receiverName", "")),
            receiver_phone=str(delivery.get("receiverPhone", "")),
            receiver_address=str(delivery.get("deliveryAddress", "")),
            expect_time=str(delivery.get("expectTime", "")),
            item_count=sum(item.quantity for item in order_items),
            goods_total_fen=goods_total_fen,
            items=normalize_delivery_quote_items(
                DeliveryQuoteItem(
                    product_id=item.product_id,
                    quantity=item.quantity,
                )
                for item in order_items
            ),
        )
        if build_delivery_request_hash(quote_request) != quote.request_hash:
            raise ValueError("配送报价与当前收货信息不一致，请重新报价")

    def _goods_total_fen(self, order_items: list[NormalizedOrderItem]) -> int:
        return sum(item.price_fen * item.quantity for item in order_items)


__all__ = ["OrderCreationService"]
