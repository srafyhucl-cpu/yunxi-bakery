"""店员认证 API。"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.staff._auth import (
    build_staff_dependency,
    clear_staff_session_cookie,
    set_staff_session_cookie,
)
from app.middleware.edge_protection import extract_client_ip
from app.models.staff import StaffPrincipal
from app.service.edge_protection import (
    attempt_admin_login,
    clear_admin_login_failures,
)
from app.service.staff_auth import StaffAuthService


def _client_key(request: Request) -> str:
    """店员登录按来源 IP 使用独立限流键。"""
    return f"staff:{extract_client_ip(request)}"


def create_staff_auth_router(service: StaffAuthService) -> APIRouter:
    """创建店员登录、当前身份与退出路由。"""
    router = APIRouter(prefix="/api/v1/staff", tags=["staff-auth"])
    require_staff = build_staff_dependency(service)

    @router.post("/auth/login")
    async def staff_login(
        request: Request,
        payload: dict[str, Any],
    ) -> JSONResponse:
        client_key = _client_key(request)
        # attempt_admin_login 原子完成“检查 + 记录一次尝试”，失败即已计数，
        # 失败分支不得再次记录，否则一次失败会被记两次。
        if not await attempt_admin_login(client_key):
            raise HTTPException(status_code=429, detail="登录尝试过于频繁")
        phone = str(payload.get("phone", "")).strip()
        pin = str(payload.get("pin", "")).strip()
        try:
            principal = await service.login(phone, pin)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        try:
            token = service.issue_session_token(principal)
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        await clear_admin_login_failures(client_key)
        response = JSONResponse(
            {
                "ok": True,
                "data": {
                    "staffId": principal.id,
                    "name": principal.name,
                    "role": principal.role,
                },
            }
        )
        set_staff_session_cookie(response, token)
        return response

    @router.get("/auth/me")
    async def staff_me(
        principal: StaffPrincipal = Depends(require_staff),
    ) -> dict:
        return {
            "ok": True,
            "data": {
                "staffId": principal.id,
                "name": principal.name,
                "phone": principal.phone,
                "role": principal.role,
                "tenantId": principal.tenant_id,
            },
        }

    @router.post("/auth/logout")
    async def staff_logout() -> JSONResponse:
        response = JSONResponse({"ok": True, "message": "已退出登录"})
        clear_staff_session_cookie(response)
        return response

    return router


__all__ = ["create_staff_auth_router"]
