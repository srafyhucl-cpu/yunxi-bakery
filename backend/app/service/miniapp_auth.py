"""小程序登录兼容入口。"""

from app.service.channels.storefront.auth import (
    StorefrontAuthService as MiniappAuthService,
)


__all__ = ["MiniappAuthService"]
