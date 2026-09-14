"""前台商品 API 路由。"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from app.service.catalog import CatalogApplicationService


def create_storefront_catalog_router(service: CatalogApplicationService) -> APIRouter:
    """创建前台商品公开路由。"""
    router = APIRouter(prefix="/api/v1/miniapp", tags=["miniapp-catalog"])

    @router.get("/products")
    async def list_products(
        ids: str = "",
        categoryId: str = "",
        featured: bool = False,
        sort: str = "",
        limit: int = 50,
        offset: int = Query(default=0, ge=0),
        keyword: str = Query(default="", max_length=50),
    ) -> dict[str, Any]:
        page = await service.list_products_page(
            ids=ids,
            category_id=categoryId,
            featured=featured,
            sort=sort,
            limit=limit,
            offset=offset,
            keyword=keyword,
        )
        return {"code": 0, "data": page.items, "meta": page.meta()}

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
