"""前台商品 API 路由。"""

from typing import Any

from fastapi import APIRouter, HTTPException, Response

from app.service.catalog import CatalogApplicationService


def create_storefront_catalog_router(service: CatalogApplicationService) -> APIRouter:
    """创建前台商品公开路由。"""
    router = APIRouter(prefix="/api/v1/miniapp", tags=["miniapp-catalog"])

    @router.get("/products")
    async def list_products(
        ids: str = "",
        categoryId: str = "",
        featured: bool = False,
    ) -> dict[str, Any]:
        return {
            "code": 0,
            "data": await service.list_products(
                ids=ids,
                category_id=categoryId,
                featured=featured,
            ),
        }

    @router.get("/product-categories")
    async def list_product_categories() -> dict[str, Any]:
        return {"code": 0, "data": await service.list_categories()}

    @router.get("/products/{product_id}/image")
    async def get_product_image(product_id: str) -> Response:
        image = await service.fetch_product_image(product_id)
        if image is None:
            raise HTTPException(status_code=404, detail="Product image not found")
        return Response(content=image.content, media_type=image.content_type)

    @router.get("/products/{product_id}")
    async def get_product(product_id: str) -> dict[str, Any]:
        return {"code": 0, "data": await service.get_product(product_id)}

    return router
