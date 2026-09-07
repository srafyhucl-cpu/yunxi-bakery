"""前台支付 API 路由。"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.service.order import OrderApplicationService
from app.service.order.refund_notification import is_terminal_success_kind


def refund_result_to_http_status(result: dict[str, Any]) -> int:
    """退款业务结果映射为微信协议 HTTP 状态。

    已完整记录事件/案件（rejected_recorded）、重复（duplicate）与已确认
    （acknowledged）必须返回成功确认，避免微信持续重试；签名无效等
    抛出的 ValueError 由调用方转为 400 触发重试或人工介入。
    """
    kind = str(result.get("kind", "") or "")
    if not kind:
        if result.get("duplicate"):
            return 200
        if result.get("rejected"):
            return 200
        return 200
    return 200 if is_terminal_success_kind(kind) else 400


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

    @router.post("/wechat/refund-notify")
    async def wechat_refund_notify(request: Request) -> dict[str, Any]:
        raw_body = await request.body()
        headers = {key.lower(): value for key, value in request.headers.items()}
        try:
            result = await service.handle_wechat_refund_notify(
                raw_body=raw_body, headers=headers
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        status = refund_result_to_http_status(
            result if isinstance(result, dict) else {}
        )
        if status != 200:
            raise HTTPException(status_code=status, detail="退款通知需稍后重试")
        return {"code": "SUCCESS", "message": "成功"}

    return router
