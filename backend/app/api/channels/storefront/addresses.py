"""前台收货地址 API。"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.channels.storefront._user import (
    authenticate_storefront_request,
    require_storefront_user_id,
)
from app.service.customer import CustomerAddressService


def create_storefront_addresses_router(service: CustomerAddressService) -> APIRouter:
    """创建前台地址簿路由。"""
    router = APIRouter(
        prefix="/api/v1/miniapp/addresses",
        tags=["miniapp-addresses"],
        dependencies=[Depends(authenticate_storefront_request)],
    )

    @router.get("")
    async def list_addresses(
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        return {
            "code": 0,
            "data": await service.list_addresses(
                require_storefront_user_id(x_miniapp_user_id)
            ),
        }

    @router.post("")
    async def save_address(
        payload: dict[str, Any],
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            item = await service.save_address(
                payload, require_storefront_user_id(x_miniapp_user_id)
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": item}

    @router.post("/{address_id}/default")
    async def set_default_address(
        address_id: str,
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            item = await service.set_default(
                address_id, require_storefront_user_id(x_miniapp_user_id)
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"code": 0, "data": item}

    @router.delete("/{address_id}")
    async def delete_address(
        address_id: str,
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            items = await service.delete_address(
                address_id, require_storefront_user_id(x_miniapp_user_id)
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"code": 0, "data": items}

    return router
