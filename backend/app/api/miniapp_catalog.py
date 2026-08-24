"""小程序商品 API 兼容入口。"""

from app.api.channels.storefront.catalog import (
    create_storefront_catalog_router as create_miniapp_catalog_router,
)

__all__ = ["create_miniapp_catalog_router"]
