"""订单后台状态流转服务。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime

from app.models.order import Order, OrderStatus
from app.repository.order_repo import OrderRepo
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_state import PAYMENT_STATUS_PAID, payment_status_value
from app.service.order.timeline import OrderTimelineService

if TYPE_CHECKING:
    from app.service.stored_value import StoredValueService


ADMIN_ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.PENDING.value: {
        OrderStatus.CONFIRMED.value,
        OrderStatus.CANCELLED.value,
    },
    OrderStatus.CONFIRMED.value: {
        OrderStatus.MAKING.value,
        OrderStatus.CANCELLED.value,
    },
    OrderStatus.MAKING.value: {OrderStatus.DELIVERING.value, OrderStatus.DONE.value},
    OrderStatus.DELIVERING.value: {OrderStatus.DONE.value},
    OrderStatus.DONE.value: set(),
    OrderStatus.CANCELLED.value: set(),
}

STATUS_EVENT_NOTES = {
    OrderStatus.PENDING.value: "用户提交订单",
    OrderStatus.CONFIRMED.value: "后台确认订单",
    OrderStatus.MAKING.value: "后台标记制作中",
    OrderStatus.DELIVERING.value: "后台标记配送/待取",
    OrderStatus.DONE.value: "后台完成订单",
    OrderStatus.CANCELLED.value: "后台取消订单",
}


class OrderAdminStatusService:
    """负责后台订单履约状态流转。"""

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

    async def update_admin_order_status(self, order_id: str, status: str) -> dict:
        """后台更新订单履约状态。"""
        target_status = self._normalize_status(status)
        order = await self._get_order(order_id)
        current_status = self._status_value(order.status)
        if target_status == current_status:
            return await self._timeline_service.serialize(order)
        if not self._can_transition(current_status, target_status):
            raise ValueError("当前订单状态不允许切换到目标状态")
        if target_status == OrderStatus.CANCELLED.value:
            updated = await self._cancel_order(order_id)
            if updated is None:
                latest = await self._get_order(order_id)
                if self._status_value(latest.status) == OrderStatus.CANCELLED.value:
                    return await self._timeline_service.serialize(latest)
                if payment_status_value(latest) == PAYMENT_STATUS_PAID:
                    raise ValueError("已支付订单不允许取消")
                raise ValueError("当前订单状态不允许切换到目标状态")
            await self._refund_balance(updated)
            await self._refund_points(updated)
            await self._clear_coupon(updated)
        else:
            updated = await self._update_status(order_id, target_status)
        await self._release_inventory_if_needed(updated, target_status)
        await self._timeline_service.record_event(
            order_id=order_id,
            status=target_status,
            operator="admin",
            note=STATUS_EVENT_NOTES.get(target_status, "订单状态更新"),
            created_at=updated.updated_at,
        )
        return await self._timeline_service.serialize(updated)

    async def _get_order(self, order_id: str) -> Order:
        order = await self._order_repo.get_order(order_id)
        if order is None:
            raise ValueError("订单不存在")
        return order

    def _normalize_status(self, status: str) -> str:
        value = str(status or "").strip()
        allowed = {item.value for item in OrderStatus}
        if value not in allowed:
            raise ValueError("订单状态不支持")
        return value

    def _can_transition(self, current_status: str, target_status: str) -> bool:
        return target_status in ADMIN_ALLOWED_STATUS_TRANSITIONS.get(
            current_status,
            set(),
        )

    async def _update_status(self, order_id: str, target_status: str) -> Order:
        updated = await self._order_repo.update_status(
            order_id,
            target_status,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        if updated is None:
            raise ValueError("订单不存在")
        return updated

    async def _cancel_order(self, order_id: str) -> Order | None:
        return await self._order_repo.cancel_unpaid_order(
            order_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    async def _refund_balance(self, order: Order) -> None:
        """后台取消组合支付订单时原路退回已扣储值余额。"""
        if self._stored_value_service is not None:
            await self._stored_value_service.refund_order_balance(order)

    async def _refund_points(self, order: Order) -> None:
        """后台取消时按支付快照退回积分并收回已发积分。"""
        from app.service.points.payment import PointsPaymentService

        await PointsPaymentService(order_repo=self._order_repo).refund_points(order)

    async def _clear_coupon(self, order: Order) -> None:
        """未支付取消只清券快照，不写 BACK。"""
        from app.service.coupon import CouponService

        await CouponService(order_repo=self._order_repo).clear_applied(order)

    async def _release_inventory_if_needed(
        self,
        order: Order,
        target_status: str,
    ) -> None:
        if target_status != OrderStatus.CANCELLED.value:
            return
        await self._inventory_service.release_reserved_inventory(
            self._inventory_service.items_from_order(order)
        )

    def _status_value(self, status: object) -> str:
        return status.value if hasattr(status, "value") else str(status)


__all__ = [
    "ADMIN_ALLOWED_STATUS_TRANSITIONS",
    "OrderAdminStatusService",
    "STATUS_EVENT_NOTES",
]
