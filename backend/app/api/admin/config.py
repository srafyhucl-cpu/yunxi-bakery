"""
店铺配置管理路由。

包含：
- 主推款管理页面与 API（Issue 1）
- 商品上下架管理页面与 API（Issue 3）
"""

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.api.admin import verify_token
from app.service.admin import AdminService


def _serialize_product_entry(e) -> dict:
    """序列化商品知识条目。"""
    return {
        "id": e.id,
        "category": e.category,
        "content_type": e.content_type,
        "title": e.title,
        "content": e.content,
        "keywords": e.keywords,
        "priority": e.priority,
        "is_active": e.is_active,
        "youzan_item_id": e.youzan_item_id,
        "last_sync_source": e.last_sync_source,
        "last_sync_ref": e.last_sync_ref,
        "vector_sync_status": e.vector_sync_status,
        "updated_at": e.updated_at,
        "price_fen": getattr(e, "price_fen", None),
        "stock": getattr(e, "stock", None),
        "sold_num": getattr(e, "sold_num", 0),
        "item_no": getattr(e, "item_no", ""),
    }


def create_shop_config_router(admin_service: AdminService) -> APIRouter:
    """创建店铺配置相关路由。"""
    router = APIRouter(tags=["admin-config"])
    api_router = APIRouter(prefix="/api/v1/admin", dependencies=[Depends(verify_token)])

    # ────────────── 主推款配置 API ──────────────

    @api_router.get("/shop-config/featured-products")
    async def get_featured_products(
        authorization: str | None = Header(default=None),
    ) -> dict:

        return {"code": 0, "data": await admin_service.get_featured_products()}

    @api_router.post("/shop-config/featured-products")
    async def set_featured_products(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict:

        raw = await request.body()
        body = json.loads(raw.decode("utf-8"))
        products: list[str] = body.get("products", [])
        products = [p.strip() for p in products if p.strip()]
        await admin_service.set_featured_products(products)
        return {"code": 0, "message": "已保存", "data": products}

    @api_router.get("/shop-config/operations")
    async def get_shop_operations(
        authorization: str | None = Header(default=None),
    ) -> dict:

        return {"code": 0, "data": await admin_service.get_shop_operations()}

    @api_router.put("/shop-config/operations")
    async def set_shop_operations(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict:

        raw = await request.body()
        body = json.loads(raw.decode("utf-8"))
        try:
            operations = await admin_service.set_shop_operations(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "code": 0,
            "message": "已保存",
            "data": operations,
        }

    # ────────────── 商品上下架 API ──────────────

    @api_router.get("/products")
    async def get_products(
        page: int = 1,
        search: str = "",
        is_active: str = "",
        sync_source: str = "",
        vector_sync_status: str = "",
        featured_only: bool = False,
        youzan_item_id: str = "",
        item_no: str = "",
        keyword_filter: str = "",
        sort_by: str = "",
        sort_order: str = "desc",
        authorization: str | None = Header(default=None),
    ) -> dict:

        limit = 30
        offset = (page - 1) * limit
        active_filter: int | None = None
        if is_active == "1":
            active_filter = 1
        elif is_active == "0":
            active_filter = 0
        featured_filter: list[str] | None = None
        if featured_only:
            featured_filter = await admin_service.get_featured_products()
        entries = await admin_service.get_all_products(
            search=search,
            limit=limit,
            offset=offset,
            is_active=active_filter,
            sync_source=sync_source,
            vector_sync_status=vector_sync_status,
            featured_titles=featured_filter,
            youzan_item_id_filter=youzan_item_id,
            keyword_filter=keyword_filter,
            item_no_filter=item_no,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        total = await admin_service.count_products(
            search=search,
            is_active=active_filter,
            sync_source=sync_source,
            vector_sync_status=vector_sync_status,
            featured_titles=featured_filter,
            youzan_item_id_filter=youzan_item_id,
            keyword_filter=keyword_filter,
            item_no_filter=item_no,
        )
        total_active = await admin_service.count_products(is_active=1)
        total_inactive = await admin_service.count_products(is_active=0)
        return {
            "code": 0,
            "total": total,
            "total_active": total_active,
            "total_inactive": total_inactive,
            "data": [_serialize_product_entry(e) for e in entries],
            "page": page,
            "page_size": limit,
        }

    @api_router.post("/products/{product_id}/toggle-active")
    async def toggle_product_active(
        product_id: int,
        authorization: str | None = Header(default=None),
    ) -> dict:

        entry = await admin_service.get_product(product_id)
        if not entry:
            raise HTTPException(status_code=404, detail="条目不存在")
        new_status = await admin_service.toggle_product_active(product_id)
        return {"code": 0, "is_active": new_status, "title": entry.title}

    @api_router.get("/settings/summary")
    async def get_settings_summary(
        authorization: str | None = Header(default=None),
    ) -> dict:

        return {"code": 0, "data": await admin_service.get_settings_summary()}

    @router.get("/api/v1/miniapp/shop-settings")
    async def get_miniapp_shop_settings() -> dict:

        return {"code": 0, "data": await admin_service.get_shop_operations()}

    router.include_router(api_router)
    return router
