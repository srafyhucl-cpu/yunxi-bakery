"""订单未支付关闭服务。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime, timedelta

from app.models.order import Order, OrderStatus
from app.repository.order_repo import OrderRepo
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_state import (
    PAYMENT_STATUS_EXPIRED,
    PAYMENT_STATUS_PARTIAL,
    PAYMENT_STATUS_UNPAID,
    PAYMENT_TIMEOUT_MINUTES,
    TIME_FORMAT,
    dumps_payment,
    loads_payment,
    parse_time,
    status_value,
)
from app.service.order.timeline import OrderTimelineService

if TYPE_CHECKING:
    from app.service.stored_value import StoredValueService


ADMIN_EXPIRE_NOTE = "后台关闭未支付订单"
SYSTEM_TIMEOUT_EXPIRE_NOTE = "未支付超时自动关闭"


class OrderExpirationService:
    """负责单笔和批量未支付关闭链路。"""

    def __init__(
        self,
        order_repo: OrderRepo,
        inventory_service: OrderInventoryService,
        timeline_service: OrderTimelineService,
        stored_value_service: StoredValueService | None = None,
    ) -> None:
        self._order_repo = order_repo
        self._inventory_service = inventory_service
        self._timeline_service = timeline_service
        self._stored_value_service = stored_value_service

    async def expire_unpaid_order(self, order_id: str) -> dict:
        """后台手动关闭单笔未支付订单。"""
        order = await self._get_order(order_id)
        expired = await self._close_unpaid_order(order, datetime.now())
        if expired is not None:
            await self._record_expiration_event(
                expired,
                operator="admin",
                note=ADMIN_EXPIRE_NOTE,
            )
        return await self._serialize_order(order_id)

    async def expire_timeout_unpaid_orders(self) -> dict:
        """批量扫描并关闭超时未支付订单。"""
        candidates = await self._order_repo.list_by_status(OrderStatus.PENDING.value)
        current_time = datetime.now()
        expired_orders: list[Order] = []
        for order in candidates:
            if not self._is_expirable(order, current_time):
                continue
            expired = await self._close_unpaid_order(order, current_time)
            if expired is None:
                continue
            await self._record_expiration_event(
                expired,
                operator="system",
                note=SYSTEM_TIMEOUT_EXPIRE_NOTE,
            )
            expired_orders.append(expired)
        return {
            "expiredCount": len(expired_orders),
            "orders": [
                await self._serialize_order(order.id) for order in expired_orders
            ],
        }

    async def _get_order(self, order_id: str) -> Order:
        order = await self._order_repo.get_order(order_id)
        if order is None:
            raise ValueError("订单不存在")
        return order

    async def _close_unpaid_order(self, order: Order, now: datetime) -> Order | None:
        if not self._is_unpaid_active(order):
            return None
        payment = loads_payment(order.payment)
        timestamp = now.strftime(TIME_FORMAT)
        payment.update(
            {
                "status": PAYMENT_STATUS_EXPIRED,
                "expiredAt": timestamp,
                "expiredReason": "payment_timeout",
            }
        )
        closed = await self._order_repo.close_unpaid_order(
            order.id,
            dumps_payment(payment),
            timestamp,
        )
        if closed is None:
            return None
        await self._refund_balance(closed)
        await self._refund_points(closed)
        await self._clear_coupon(closed)
        await self._inventory_service.release_reserved_inventory(
            self._inventory_service.items_from_order(closed)
        )
        return closed

    async def _record_expiration_event(
        self,
        order: Order,
        *,
        operator: str,
        note: str,
    ) -> None:
        await self._timeline_service.record_event(
            order_id=order.id,
            status=OrderStatus.CANCELLED.value,
            operator=operator,
            note=note,
            created_at=order.updated_at,
        )

    def _is_expirable(self, order: Order, now: datetime) -> bool:
        if not self._is_unpaid_active(order):
            return False
        payment = loads_payment(order.payment)
        created_at = parse_time(str(payment.get("createdAt") or order.created_at))
        return created_at is not None and now - created_at >= timedelta(
            minutes=PAYMENT_TIMEOUT_MINUTES
        )

    @staticmethod
    def _is_unpaid_active(order: Order) -> bool:
        if status_value(order) == OrderStatus.CANCELLED.value:
            return False
        payment = loads_payment(order.payment)
        return str(payment.get("status", PAYMENT_STATUS_UNPAID)) in (
            PAYMENT_STATUS_UNPAID,
            PAYMENT_STATUS_PARTIAL,
        )

    async def _refund_balance(self, order: Order) -> None:
        """组合支付超时关闭时原路退回已扣储值余额。"""
        if self._stored_value_service is not None:
            await self._stored_value_service.refund_order_balance(order)

    async def _refund_points(self, order: Order) -> None:
        """超时关闭时按支付快照退回积分并收回已发积分。"""
        from app.service.points.payment import PointsPaymentService

        await PointsPaymentService(order_repo=self._order_repo).refund_points(order)

    async def _clear_coupon(self, order: Order) -> None:
        """未支付取消只清券快照，不写 BACK。"""
        from app.service.coupon import CouponService

        await CouponService(order_repo=self._order_repo).clear_applied(order)

    async def _serialize_order(self, order_id: str) -> dict:
        order = await self._order_repo.get_order(order_id)
        if order is None:
            raise ValueError("订单不存在")
        return await self._timeline_service.serialize(order)


__all__ = [
    "ADMIN_EXPIRE_NOTE",
    "OrderExpirationService",
    "SYSTEM_TIMEOUT_EXPIRE_NOTE",
]
