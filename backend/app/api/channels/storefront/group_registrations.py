"""前台客户群登记 API。"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.channels.storefront._user import (
    authenticate_storefront_request,
    require_storefront_user_id,
)
from app.service.customer import CustomerGroupOperationsService


def create_storefront_group_registrations_router(
    service: CustomerGroupOperationsService,
) -> APIRouter:
    """创建前台客户群登记路由。"""
    router = APIRouter(
        prefix="/api/v1/miniapp/group-registrations",
        tags=["miniapp-group-registrations"],
        dependencies=[Depends(authenticate_storefront_request)],
    )

    @router.post("")
    async def submit_registration(
        payload: dict[str, Any],
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            item = await service.submit_registration(
                payload,
                user_id=require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": item}

    @router.get("/me")
    async def list_my_registrations(
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        return {
            "code": 0,
            "data": await service.list_my_registrations(
                user_id=require_storefront_user_id(x_miniapp_user_id),
            ),
        }

    return router
