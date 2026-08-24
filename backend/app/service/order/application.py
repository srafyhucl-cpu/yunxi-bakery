"""订单领域应用服务。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.constants.storefront import STOREFRONT_DEMO_USER_ID
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.repository.config_repo import ConfigRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order.cancellation import OrderCancellationService
from app.service.order.creation import OrderCreationService
from app.service.order.expiration import OrderExpirationService
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment import OrderPaymentService
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.read_models import (
    ADMIN_ORDER_BOARD_FILTERS,
    normalize_board_filter,
    summarize_board_row,
)
from app.service.order.schedule import OrderScheduleService
from app.service.order.serialization import OrderSerializationService
from app.service.order.status_flow import OrderAdminStatusService
from app.service.order.timeline import OrderTimelineService
from app.service.shop_operations import ShopOperationsService

if TYPE_CHECKING:
    from app.service.stored_value import StoredValueService


DEFAULT_PAGE_SIZE = 30


class OrderApplicationService:
    """订单领域应用服务，优先承接读链路与后台看板。"""

    def __init__(
        self,
        order_repo: OrderRepo,
        session_repo: SessionRepo,
        product_repo: YouzanProductRepo,
        inventory_repo: YouzanInventoryRepo,
        config_repo: ConfigRepo,
        event_repo: OrderEventRepo | None = None,
        stored_value_service: StoredValueService | None = None,
    ) -> None:
        self._order_repo = order_repo
        self._serialization_service = OrderSerializationService()
        inventory_service = OrderInventoryService(product_repo, inventory_repo)
        schedule_service = OrderScheduleService(ShopOperationsService(config_repo))
        payment_service = OrderPaymentRuntimeService(
            order_repo,
            event_repo=event_repo,
        )
        self._timeline_service = OrderTimelineService(
            self._serialization_service,
            event_repo,
        )
        self._creation_service = OrderCreationService(
            order_repo=order_repo,
            session_repo=session_repo,
            inventory_service=inventory_service,
            schedule_service=schedule_service,
            timeline_service=self._timeline_service,
        )
        self._payment_service = OrderPaymentService(payment_service)
        self._cancellation_service = OrderCancellationService(
            order_repo=order_repo,
            inventory_service=inventory_service,
            timeline_service=self._timeline_service,
            stored_value_service=stored_value_service,
        )
        self._admin_status_service = OrderAdminStatusService(
            order_repo=order_repo,
            inventory_service=inventory_service,
            timeline_service=self._timeline_service,
            stored_value_service=stored_value_service,
        )
        self._expiration_service = OrderExpirationService(
            order_repo=order_repo,
            inventory_service=inventory_service,
            timeline_service=self._timeline_service,
            stored_value_service=stored_value_service,
        )

    async def create_order(
        self,
        payload: dict,
        *,
        user_id: str = STOREFRONT_DEMO_USER_ID,
    ) -> dict:
        """由订单领域接管下单创建链路。"""
        async with self._order_repo.transaction():
            return await self._creation_service.create_order(payload, user_id=user_id)

    async def list_user_orders(
        self,
        *,
        user_id: str = STOREFRONT_DEMO_USER_ID,
    ) -> list[dict]:
        """读取当前小程序用户订单。"""
        orders = await self._order_repo.list_by_user(user_id)
        return [self._serialization_service.serialize(order) for order in orders]

    async def get_user_order(
        self,
        order_id: str,
        *,
        user_id: str = STOREFRONT_DEMO_USER_ID,
    ) -> dict:
        """读取当前小程序用户的单个订单。"""
        order = await self._order_repo.get_order(order_id)
        if order is None or order.user_id != user_id:
            raise ValueError("订单不存在")
        return await self._timeline_service.serialize(order)

    async def cancel_user_order(
        self,
        order_id: str,
        *,
        user_id: str = STOREFRONT_DEMO_USER_ID,
    ) -> dict:
        """由订单领域接管小程序用户取消链路。"""
        async with self._order_repo.transaction():
            return await self._cancellation_service.cancel_user_order(
                order_id,
                user_id=user_id,
            )

    async def confirm_mock_payment(
        self,
        order_id: str,
        *,
        user_id: str = STOREFRONT_DEMO_USER_ID,
    ) -> dict:
        """由订单领域接管 mock 支付链路。"""
        async with self._order_repo.transaction():
            return await self._payment_service.confirm_mock_payment(
                order_id,
                user_id=user_id,
            )

    async def prepare_payment(
        self,
        order_id: str,
        *,
        user_id: str = STOREFRONT_DEMO_USER_ID,
    ) -> dict:
        """由订单领域接管支付准备链路。"""
        return await self._payment_service.prepare_payment(
            order_id,
            user_id=user_id,
        )

    async def handle_wechat_payment_notify(
        self,
        *,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> dict:
        """由订单领域接管微信支付通知链路。"""
        async with self._order_repo.transaction():
            return await self._payment_service.handle_wechat_payment_notify(
                raw_body=raw_body,
                headers=headers,
            )

    async def expire_unpaid_order(self, order_id: str) -> dict:
        """由订单领域接管后台关闭未支付链路。"""
        async with self._order_repo.transaction():
            return await self._expiration_service.expire_unpaid_order(order_id)

    async def expire_timeout_unpaid_orders(self) -> dict:
        """由订单领域接管超时未支付扫描链路。"""
        async with self._order_repo.transaction():
            return await self._expiration_service.expire_timeout_unpaid_orders()

    async def list_admin_orders(
        self,
        *,
        page: int = 1,
        keyword: str = "",
        status: str = "",
        board_filter: str = "",
    ) -> dict:
        """后台分页读取订单。"""
        safe_page = max(page, 1)
        normalized_board_filter = normalize_board_filter(board_filter)
        orders = await self._order_repo.list_orders(
            keyword=keyword,
            status=status,
            board_filter=normalized_board_filter,
            limit=DEFAULT_PAGE_SIZE,
            offset=(safe_page - 1) * DEFAULT_PAGE_SIZE,
        )
        total = await self._order_repo.count_orders(
            keyword=keyword,
            status=status,
            board_filter=normalized_board_filter,
        )
        return {
            "items": [self._serialization_service.serialize(order) for order in orders],
            "total": total,
            "page": safe_page,
            "pageSize": DEFAULT_PAGE_SIZE,
        }

    async def get_admin_order_summary(self, *, keyword: str = "") -> dict:
        """后台读取订单经营看板汇总。"""
        rows = await self._order_repo.summarize_orders(keyword=keyword)
        cards = []
        total_count = 0
        total_fen = 0
        for config in ADMIN_ORDER_BOARD_FILTERS:
            count, amount_fen = summarize_board_row(config["key"], rows)
            if config["key"] == "all":
                total_count = count
                total_fen = amount_fen
            cards.append({**config, "count": count, "totalFen": amount_fen})
        return {
            "cards": cards,
            "totalCount": total_count,
            "totalFen": total_fen,
            "keyword": keyword,
        }

    async def get_admin_order(self, order_id: str) -> dict:
        """后台读取订单详情。"""
        order = await self._order_repo.get_order(order_id)
        if order is None:
            raise ValueError("订单不存在")
        return await self._timeline_service.serialize(order)

    async def update_admin_order_status(self, order_id: str, status: str) -> dict:
        """由订单领域接管后台状态流转链路。"""
        async with self._order_repo.transaction():
            return await self._admin_status_service.update_admin_order_status(
                order_id, status
            )


__all__ = ["OrderApplicationService"]
