"""前台顾客隐私与记忆 consent API。"""

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.channels.storefront._user import (
    authenticate_storefront_request,
    require_storefront_user_id,
)
from app.service.customer_consent import CustomerConsentService
from app.service.privacy_lifecycle import PrivacyLifecycleService


def create_storefront_privacy_router(
    service: CustomerConsentService,
    lifecycle_service: PrivacyLifecycleService | None = None,
) -> APIRouter:
    """创建顾客 consent 状态接口。"""
    router = APIRouter(
        prefix="/api/v1/miniapp/privacy",
        tags=["miniapp-privacy"],
        dependencies=[Depends(authenticate_storefront_request)],
    )

    @router.get("/consent")
    async def get_consent(
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, object]:
        user_id = require_storefront_user_id(x_miniapp_user_id)
        status = await service.get_status("miniapp", user_id)
        return {"code": 0, "status": status}

    @router.post("/consent/grant")
    async def grant_consent(
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, object]:
        user_id = require_storefront_user_id(x_miniapp_user_id)
        status = await service.grant("miniapp", user_id)
        return {"code": 0, "status": status}

    @router.post("/consent/revoke")
    async def revoke_consent(
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, object]:
        user_id = require_storefront_user_id(x_miniapp_user_id)
        status = await service.revoke("miniapp", user_id)
        return {"code": 0, "status": status}

    @router.get("/subject/export")
    async def export_subject(
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, object]:
        user_id = require_storefront_user_id(x_miniapp_user_id)
        if lifecycle_service is None:
            raise HTTPException(status_code=503, detail="隐私权利服务未就绪")
        return {"code": 0, "data": await lifecycle_service.export_subject(user_id)}

    @router.delete("/subject")
    async def delete_subject(
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, object]:
        user_id = require_storefront_user_id(x_miniapp_user_id)
        if lifecycle_service is None:
            raise HTTPException(status_code=503, detail="隐私权利服务未就绪")
        await lifecycle_service.delete_subject(user_id)
        return {"code": 0, "status": "revoked"}

    return router
