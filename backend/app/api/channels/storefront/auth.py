"""前台认证 API 路由。"""

from typing import Any

from fastapi import APIRouter, HTTPException

from app.service.channels.storefront import StorefrontAuthService


def create_storefront_auth_router(service: StorefrontAuthService) -> APIRouter:
    """创建前台认证路由。"""
    router = APIRouter(prefix="/api/v1/miniapp/auth", tags=["miniapp-auth"])

    @router.post("/login")
    async def login(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await service.login(str(payload.get("code", "")))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": result}

    @router.post("/bind-phone")
    @router.post("/claim")
    async def claim_member(
        payload: dict[str, Any],
        x_miniapp_user_id: str | None = None,
    ) -> dict[str, Any]:
        phone = str(payload.get("phone", "") or payload.get("mobile", "")).strip()
        user_id = str(payload.get("userId", "") or x_miniapp_user_id or "").strip()
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="请提供有效的微信用户身份（userId 或 x-miniapp-user-id）",
            )
        try:
            result = await service.claim_member_by_phone(user_id=user_id, phone=phone)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": result}

    return router
