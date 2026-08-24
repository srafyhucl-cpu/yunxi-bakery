"""后台顾客地址管理 API。"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.admin import verify_token
from app.service.customer import CustomerAddressService


def create_admin_addresses_router(service: CustomerAddressService) -> APIRouter:
    """创建后台顾客地址管理路由。"""
    router = APIRouter(
        prefix="/api/v1/admin/addresses",
        tags=["admin-addresses"],
        dependencies=[Depends(verify_token)],
    )

    @router.get("")
    async def list_addresses(
        page: int = 1,
        keyword: str = "",
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return {
            "code": 0,
            "data": await service.list_admin_addresses(page=page, keyword=keyword),
        }

    @router.post("")
    async def create_address(
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            return {
                "code": 0,
                "data": await service.save_admin_address(
                    payload,
                    operator=_admin_operator(authorization),
                ),
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/{address_id}")
    async def get_address(
        address_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            return {"code": 0, "data": await service.get_admin_address(address_id)}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.put("/{address_id}")
    async def update_address(
        address_id: str,
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            return {
                "code": 0,
                "data": await service.save_admin_address(
                    {**payload, "id": address_id},
                    operator=_admin_operator(authorization),
                ),
            }
        except ValueError as exc:
            status_code = 404 if str(exc) == "地址不存在" else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @router.post("/{address_id}/default")
    async def set_default_address(
        address_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            return {
                "code": 0,
                "data": await service.set_admin_default(
                    address_id,
                    operator=_admin_operator(authorization),
                ),
            }
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.delete("/{address_id}")
    async def delete_address(
        address_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            return {
                "code": 0,
                "data": await service.delete_admin_address(
                    address_id,
                    operator=_admin_operator(authorization),
                ),
            }
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router


def _admin_operator(authorization: str | None) -> str:
    token = (authorization or "").replace("Bearer ", "", 1).strip()
    return f"admin:{token[:8]}" if token else "admin"
