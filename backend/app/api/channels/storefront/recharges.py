"""前台储值充值 API 路由。"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.channels.storefront._user import (
    authenticate_storefront_request,
    require_storefront_user_id,
)
from app.service.stored_value import StoredValueService


def create_storefront_recharges_router(service: StoredValueService) -> APIRouter:
    """创建前台储值充值公开路由。"""
    router = APIRouter(
        prefix="/api/v1/miniapp/recharges",
        tags=["miniapp-recharges"],
        dependencies=[Depends(authenticate_storefront_request)],
    )

    @router.post("")
    async def create_recharge(
        payload: dict[str, Any],
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            recharge = await service.create_recharge(
                require_storefront_user_id(x_miniapp_user_id),
                amount_fen=int(payload.get("amountFen", 0)),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": recharge}

    @router.post("/{recharge_id}/mock-pay")
    async def mock_pay_recharge(
        recharge_id: str,
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            recharge = await service.confirm_mock_recharge_payment(
                recharge_id,
                user_id=require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": recharge}

    @router.post("/{recharge_id}/cancel")
    async def cancel_recharge(
        recharge_id: str,
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            recharge = await service.cancel_unpaid_recharge(
                recharge_id,
                user_id=require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": recharge}

    @router.get("")
    async def list_recharges(
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        recharges = await service.list_user_recharges(
            require_storefront_user_id(x_miniapp_user_id),
        )
        return {"code": 0, "data": recharges}

    return router


def create_storefront_balance_router(service: StoredValueService) -> APIRouter:
    """创建前台储值余额查询路由。"""
    router = APIRouter(
        prefix="/api/v1/miniapp/balance",
        tags=["miniapp-balance"],
        dependencies=[Depends(authenticate_storefront_request)],
    )

    @router.get("")
    async def get_balance(
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            balance = await service.get_user_balance(
                require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": balance}

    return router
