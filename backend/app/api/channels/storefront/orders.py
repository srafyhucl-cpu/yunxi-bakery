"""前台订单 API 路由。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.channels.storefront._user import (
    authenticate_storefront_request,
    require_storefront_user_id,
)
from app.service.order import OrderApplicationService

if TYPE_CHECKING:
    from app.service.stored_value import StoredValueService


def create_storefront_orders_router(
    service: OrderApplicationService,
    stored_value_service: StoredValueService | None = None,
) -> APIRouter:
    """创建前台订单公开路由。"""
    router = APIRouter(
        prefix="/api/v1/miniapp/orders",
        tags=["miniapp-orders"],
        dependencies=[Depends(authenticate_storefront_request)],
    )

    @router.post("")
    async def create_order(
        payload: dict[str, Any],
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            order = await service.create_order(
                payload,
                user_id=require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": order}

    @router.get("")
    async def list_orders(
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        orders = await service.list_user_orders(
            user_id=require_storefront_user_id(x_miniapp_user_id),
        )
        return {"code": 0, "data": orders}

    @router.get("/{order_id}")
    async def get_order(
        order_id: str,
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            order = await service.get_user_order(
                order_id,
                user_id=require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"code": 0, "data": order}

    @router.post("/{order_id}/cancel")
    async def cancel_order(
        order_id: str,
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            order = await service.cancel_user_order(
                order_id,
                user_id=require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if message == "订单不存在" else 400
            raise HTTPException(status_code=status_code, detail=message) from exc
        return {"code": 0, "data": order}

    @router.post("/{order_id}/mock-pay")
    async def mock_pay_order(
        order_id: str,
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            order = await service.confirm_mock_payment(
                order_id,
                user_id=require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if message == "订单不存在" else 400
            raise HTTPException(status_code=status_code, detail=message) from exc
        return {"code": 0, "data": order}

    @router.post("/{order_id}/pay-with-balance")
    async def pay_order_with_balance(
        order_id: str,
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        if stored_value_service is None:
            raise HTTPException(status_code=400, detail="储值支付未启用")
        try:
            payment = await stored_value_service.pay_order_with_balance(
                order_id,
                user_id=require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if message == "订单不存在" else 400
            raise HTTPException(status_code=status_code, detail=message) from exc
        return {"code": 0, "data": payment}

    @router.post("/{order_id}/prepare-combined-payment")
    async def prepare_combined_payment(
        order_id: str,
        payload: dict[str, Any],
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        if stored_value_service is None:
            raise HTTPException(status_code=400, detail="储值支付未启用")
        try:
            payment = await stored_value_service.prepare_combined_payment(
                order_id,
                user_id=require_storefront_user_id(x_miniapp_user_id),
                balance_fen=int(payload.get("balanceFen", 0)),
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if message == "订单不存在" else 400
            raise HTTPException(status_code=status_code, detail=message) from exc
        return {"code": 0, "data": payment}

    @router.post("/{order_id}/prepare-payment")
    async def prepare_payment(
        order_id: str,
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            payment = await service.prepare_payment(
                order_id,
                user_id=require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if message == "订单不存在" else 400
            raise HTTPException(status_code=status_code, detail=message) from exc
        return {"code": 0, "data": payment}

    return router
