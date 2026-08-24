"""小程序客户群登记 API 兼容入口。"""

from app.api.channels.storefront.group_registrations import (
    create_storefront_group_registrations_router as create_miniapp_group_registrations_router,
)

__all__ = ["create_miniapp_group_registrations_router"]
