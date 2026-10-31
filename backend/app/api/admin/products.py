"""
商品管理后台 API 路由。

职责：
- 提供商品全量对账触发接口
- 对账完成后自动批量同步 pending 向量状态
"""

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile

from app.api.admin import verify_token
from app.service.catalog.product_admin import ProductAdminService
from app.service.knowledge_sync import KnowledgeSyncService
from app.service.youzan.product_reconciler import ProductReconcileService


def create_admin_products_router(
    reconcile_service: ProductReconcileService,
    knowledge_sync_service: KnowledgeSyncService,
    product_admin_service: ProductAdminService,
) -> APIRouter:
    """创建商品管理 API 路由。"""
    router = APIRouter(
        prefix="/api/v1/admin/products",
        tags=["admin-products"],
        dependencies=[Depends(verify_token)],
    )

    @router.post("/reconcile")
    async def trigger_reconcile(
        authorization: str | None = Header(default=None),
    ) -> dict:
        """触发商品全量对账，并在对账完成后批量同步所有 pending 向量状态。"""

        reconcile_result = await reconcile_service.run()
        sync_result = await knowledge_sync_service.sync_all_pending()
        return {"code": 0, "data": {**reconcile_result, "vector_sync": sync_result}}

    @router.get("/{item_id}")
    async def get_product(item_id: str) -> dict:
        """读取商品规格数据与当前生效的履约方式，供后台编辑使用。"""
        try:
            product = await product_admin_service.get_product(item_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if product is None:
            raise HTTPException(status_code=404, detail="商品不存在")
        return {"code": 0, "data": product}

    @router.patch("/{item_id}/fulfillment-mode")
    async def set_fulfillment_mode(item_id: str, payload: dict) -> dict:
        """按商品覆盖履约方式：auto 自动推导 / preorder 预订 / direct 现货。"""
        try:
            result = await product_admin_service.set_fulfillment_mode(
                item_id, str(payload.get("mode") or "")
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": result}

    @router.post("")
    async def create_product(payload: dict) -> dict:
        """新建自有商品；编号沿用整数 item_id，历史订单不受影响。"""
        try:
            product = await product_admin_service.create_product(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": product}

    @router.put("/{item_id}")
    async def save_product(item_id: str, payload: dict) -> dict:
        """保存商品编辑结果（规格表、属性组、标题价格库存、履约方式）。"""
        try:
            product = await product_admin_service.save_product(item_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": product}

    @router.post("/{item_id}/image")
    async def upload_product_image(item_id: str, file: UploadFile = File(...)) -> dict:
        """上传商品图，存到服务器本地目录并写回 image_local。"""
        content = await file.read()
        try:
            result = await product_admin_service.save_image(
                item_id, content, file.content_type or ""
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": result}

    return router
