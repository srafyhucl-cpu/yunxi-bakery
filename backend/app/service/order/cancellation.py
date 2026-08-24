"""订单取消领域服务。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime

from app.constants.storefront import STOREFRONT_DEMO_USER_ID
from app.models.order import Order, OrderStatus
from app.repository.order_repo import OrderRepo
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_state import PAYMENT_STATUS_PAID, payment_status_value
from app.service.order.timeline import OrderTimelineService

if TYPE_CHECKING:
    from app.service.stored_value import StoredValueService


USER_CANCELABLE_STATUSES = {
    OrderStatus.PENDING.value,
    OrderStatus.CONFIRMED.value,
}


class OrderCancellationService:
    """负责小程序用户取消订单链路。"""

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

    async def cancel_user_order(
        self,
        order_id: str,
        *,
        user_id: str = STOREFRONT_DEMO_USER_ID,
    ) -> dict:
        """小程序用户取消自己的未制作订单。"""
        order = await self._get_owned_order(order_id, user_id=user_id)
        current_status = self._status_value(order.status)
        if current_status == OrderStatus.CANCELLED.value:
            return await self._timeline_service.serialize(order)
        if payment_status_value(order) == PAYMENT_STATUS_PAID:
            raise ValueError("已支付订单不允许取消")
        if current_status not in USER_CANCELABLE_STATUSES:
            raise ValueError("当前订单状态不允许用户取消")
        updated = await self._cancel_order(order_id)
        if updated is None:
            latest = await self._get_owned_order(order_id, user_id=user_id)
            if self._status_value(latest.status) == OrderStatus.CANCELLED.value:
                return await self._timeline_service.serialize(latest)
            if payment_status_value(latest) == PAYMENT_STATUS_PAID:
                raise ValueError("已支付订单不允许取消")
            raise ValueError("当前订单状态不允许用户取消")
        await self._refund_balance(updated)
        await self._refund_points(updated)
        await self._clear_coupon(updated)
        await self._timeline_service.record_event(
            order_id=order_id,
            status=OrderStatus.CANCELLED.value,
            operator=f"miniapp:{user_id}",
            note="用户取消订单",
            created_at=updated.updated_at,
        )
        await self._release_inventory(updated)
        return await self._timeline_service.serialize(updated)

    async def _get_owned_order(self, order_id: str, *, user_id: str) -> Order:
        order = await self._order_repo.get_order(order_id)
        if order is None or order.user_id != user_id:
            raise ValueError("订单不存在")
        return order

    async def _cancel_order(self, order_id: str) -> Order | None:
        return await self._order_repo.cancel_unpaid_order(
            order_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    async def _refund_balance(self, order: Order) -> None:
        """组合支付取消时原路退回已扣储值余额。"""
        if self._stored_value_service is not None:
            await self._stored_value_service.refund_order_balance(order)

    async def _refund_points(self, order: Order) -> None:
        """取消时按支付快照退回积分并收回已发积分。"""
        from app.service.points.payment import PointsPaymentService

        await PointsPaymentService(order_repo=self._order_repo).refund_points(order)

    async def _clear_coupon(self, order: Order) -> None:
        """未支付取消只清券快照，不写 BACK。"""
        from app.service.coupon import CouponService

        await CouponService(order_repo=self._order_repo).clear_applied(order)

    async def _release_inventory(self, order: Order) -> None:
        await self._inventory_service.release_reserved_inventory(
            self._inventory_service.items_from_order(order)
        )

    def _status_value(self, status: object) -> str:
        return status.value if hasattr(status, "value") else str(status)


__all__ = ["OrderCancellationService", "USER_CANCELABLE_STATUSES"]
