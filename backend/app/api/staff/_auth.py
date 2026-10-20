"""店员 API 会话边界：独立 Cookie 与主体校验。"""

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request
from starlette.responses import Response

from app.config import settings
from app.models.staff import StaffPrincipal
from app.service.staff_auth import StaffAuthService

STAFF_SESSION_COOKIE = "staff_session"


def set_staff_session_cookie(response: Response, token: str) -> None:
    """写入独立店员会话 Cookie，不复用后台管理员 Cookie。"""
    response.set_cookie(
        key=STAFF_SESSION_COOKIE,
        value=token,
        max_age=settings.STAFF_SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.ADMIN_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )


def clear_staff_session_cookie(response: Response) -> None:
    """删除店员会话 Cookie。"""
    response.delete_cookie(STAFF_SESSION_COOKIE, path="/")


async def require_staff(
    request: Request,
    service: StaffAuthService,
) -> StaffPrincipal:
    """从店员 Cookie 校验会话，任何失败统一返回 401。"""
    token = str(request.cookies.get(STAFF_SESSION_COOKIE, "") or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    try:
        return await service.verify_session_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def build_staff_dependency(
    service: StaffAuthService,
) -> Callable[[Request], Awaitable[StaffPrincipal]]:
    """生成绑定到具体认证服务的 FastAPI 依赖。"""

    async def _dependency(request: Request) -> StaffPrincipal:
        return await require_staff(request, service)

    return _dependency


__all__ = [
    "STAFF_SESSION_COOKIE",
    "build_staff_dependency",
    "clear_staff_session_cookie",
    "require_staff",
    "set_staff_session_cookie",
]
