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

    return router
