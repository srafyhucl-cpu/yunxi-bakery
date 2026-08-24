"""后台订单 API 路由。"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.admin import verify_token
from app.service.order import OrderApplicationService


def create_admin_orders_router(service: OrderApplicationService) -> APIRouter:
    """创建后台订单路由。"""
    router = APIRouter(
        prefix="/api/v1/admin/orders",
        tags=["admin-orders"],
        dependencies=[Depends(verify_token)],
    )

    @router.get("")
    async def list_orders(
        page: int = 1,
        keyword: str = "",
        status: str = "",
        boardFilter: str = "",
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return {
            "code": 0,
            "data": await service.list_admin_orders(
                page=page,
                keyword=keyword,
                status=status,
                board_filter=boardFilter,
            ),
        }

    @router.get("/summary")
    async def get_order_summary(
        keyword: str = "",
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return {
            "code": 0,
            "data": await service.get_admin_order_summary(keyword=keyword),
        }

    @router.post("/expire-timeout-unpaid")
    async def expire_timeout_unpaid_orders(
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return {"code": 0, "data": await service.expire_timeout_unpaid_orders()}

    @router.get("/{order_id}")
    async def get_order(
        order_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            return {"code": 0, "data": await service.get_admin_order(order_id)}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/{order_id}/status")
    async def update_status(
        order_id: str,
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            return {
                "code": 0,
                "data": await service.update_admin_order_status(
                    order_id,
                    str(payload.get("status", "")),
                ),
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/{order_id}/expire-unpaid")
    async def expire_unpaid_order(
        order_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            return {"code": 0, "data": await service.expire_unpaid_order(order_id)}
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if message == "订单不存在" else 400
            raise HTTPException(status_code=status_code, detail=message) from exc

    return router
