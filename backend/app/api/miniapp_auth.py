"""小程序认证 API 兼容入口。"""

from app.api.channels.storefront.auth import (
    create_storefront_auth_router as create_miniapp_auth_router,
)

__all__ = ["create_miniapp_auth_router"]
