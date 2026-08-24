"""小程序商品目录兼容入口。"""

from app.service.catalog.application import (
    CatalogApplicationService as MiniappCatalogService,
    ProductImagePayload,
)

__all__ = ["MiniappCatalogService", "ProductImagePayload"]
