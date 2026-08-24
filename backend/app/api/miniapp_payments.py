"""小程序支付 API 兼容入口。"""

from app.api.channels.storefront.payments import (
    create_storefront_payments_router as create_miniapp_payments_router,
)

__all__ = ["create_miniapp_payments_router"]
