"""小程序店铺装修页面配置 API。"""

from typing import Any

from fastapi import APIRouter, Depends, Header

from app.api.admin import verify_token
from app.service.shop_page_config import ShopPageConfigService


def create_shop_page_config_router(service: ShopPageConfigService) -> APIRouter:
    """创建小程序页面装修配置路由。"""
    router = APIRouter(tags=["shop-page-config"])
    admin_router = APIRouter(
        prefix="/api/v1/admin/shop-config/pages",
        dependencies=[Depends(verify_token)],
    )
    miniapp_router = APIRouter(prefix="/api/v1/miniapp/pages")

    @admin_router.get("/{page_id}")
    async def get_admin_page_config(
        page_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return {"code": 0, "data": await service.get_admin_page(page_id)}

    @admin_router.put("/{page_id}/draft")
    async def save_page_config_draft(
        page_id: str,
        page_config: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return {"code": 0, "data": await service.save_draft(page_id, page_config)}

    @admin_router.post("/{page_id}/publish")
    async def publish_page_config(
        page_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return {"code": 0, "data": await service.publish(page_id)}

    @miniapp_router.get("/{page_id}")
    async def get_published_page_config(page_id: str) -> dict[str, Any]:
        return {"code": 0, "data": await service.get_published_page(page_id)}

    router.include_router(admin_router)
    router.include_router(miniapp_router)
    return router
