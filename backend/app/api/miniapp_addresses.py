"""小程序收货地址 API 兼容入口。"""

from app.api.channels.storefront.addresses import (
    create_storefront_addresses_router as create_miniapp_addresses_router,
)

__all__ = ["create_miniapp_addresses_router"]
