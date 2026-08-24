"""前台支付 API 路由。"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.service.order import OrderApplicationService


def create_storefront_payments_router(service: OrderApplicationService) -> APIRouter:
    """创建前台支付回调路由。"""
    router = APIRouter(prefix="/api/v1/miniapp/payments", tags=["miniapp-payments"])

    @router.post("/wechat/notify")
    async def wechat_payment_notify(request: Request) -> dict[str, Any]:
        raw_body = await request.body()
        headers = {key.lower(): value for key, value in request.headers.items()}
        try:
            await service.handle_wechat_payment_notify(
                raw_body=raw_body, headers=headers
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": "SUCCESS", "message": "成功"}

    return router
