"""
商品管理后台 API 路由。

职责：
- 提供商品全量对账触发接口
- 对账完成后自动批量同步 pending 向量状态
"""

from fastapi import APIRouter, Depends, Header

from app.api.admin import verify_token
from app.service.knowledge_sync import KnowledgeSyncService
from app.service.youzan.product_reconciler import ProductReconcileService


def create_admin_products_router(
    reconcile_service: ProductReconcileService,
    knowledge_sync_service: KnowledgeSyncService,
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

    return router
