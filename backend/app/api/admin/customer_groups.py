"""后台客户群运营 API。"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.admin import verify_token
from app.service.customer import CustomerGroupOperationsService


def create_admin_customer_groups_router(
    service: CustomerGroupOperationsService,
) -> APIRouter:
    """创建后台客户群运营路由。"""
    router = APIRouter(
        prefix="/api/v1/admin/customer-groups",
        tags=["admin-customer-groups"],
        dependencies=[Depends(verify_token)],
    )

    @router.get("")
    async def list_groups(
        keyword: str = "",
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return {"code": 0, "data": await service.list_groups(keyword=keyword)}

    @router.post("")
    async def bind_group(
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            group = await service.bind_group(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": group}

    @router.post("/campaigns")
    async def create_campaign(
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            campaign = await service.create_campaign(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": campaign}

    @router.get("/campaigns")
    async def list_campaigns(
        groupId: str = "",
        status: str = "",
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return {
            "code": 0,
            "data": await service.list_campaigns(group_id=groupId, status=status),
        }

    @router.get("/campaigns/{campaign_id}/summary")
    async def get_campaign_summary(
        campaign_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            summary = await service.get_campaign_summary(campaign_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"code": 0, "data": summary}

    @router.post("/registrations/{registration_id}/status")
    async def update_registration_status(
        registration_id: str,
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            registration = await service.update_registration_status(
                registration_id,
                str(payload.get("status", "")),
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if message == "登记不存在" else 400
            raise HTTPException(status_code=status_code, detail=message) from exc
        return {"code": 0, "data": registration}

    return router
