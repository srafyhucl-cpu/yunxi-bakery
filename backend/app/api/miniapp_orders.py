"""小程序订单 API 兼容入口。"""

from app.api.channels.storefront.orders import (
    create_storefront_orders_router as create_miniapp_orders_router,
)

__all__ = ["create_miniapp_orders_router"]
