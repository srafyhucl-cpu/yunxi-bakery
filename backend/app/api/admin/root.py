"""
管理后台页面路由与鉴权工具。

包含：
- 页面路由（登录 / 概览 / 转人工队列 / AI 对话调试页面）
- 鉴权工具函数（供子路由模块导入复用）
- create_admin_router 工厂（汇总页面路由 + AI 对话 API + 转人工 API）
"""

import hmac
import time
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Header, HTTPException, Request
from jose import JWTError, jwt

from app.config import settings
from app.service.admin import AdminService
from app.service.chat import ChatService
from app.service.transfer_manager import TransferManager

ADMIN_SESSION_COOKIE = "admin_session"
ADMIN_SESSION_ALGORITHM = "HS256"
ADMIN_SESSION_MAX_AGE_SECONDS = 1800
_admin_login_attempts: dict[str, tuple[int, float]] = {}


def is_valid_admin_token(token: str | None) -> bool:
    expected = settings.ADMIN_API_TOKEN
    if not token or not expected:
        return False
    return hmac.compare_digest(token, expected)


def issue_admin_session() -> str:
    """签发短时后台会话，不把长期管理 token 暴露给浏览器。"""
    secret = settings.ADMIN_SESSION_SECRET
    if not secret:
        raise HTTPException(status_code=503, detail="后台会话密钥未配置")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "admin",
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(seconds=settings.ADMIN_SESSION_TTL_SECONDS)).timestamp()
        ),
    }
    return jwt.encode(payload, secret, algorithm=ADMIN_SESSION_ALGORITHM)


def is_valid_admin_session(token: str | None) -> bool:
    """校验短时后台会话。"""
    if not token or not settings.ADMIN_SESSION_SECRET:
        return False
    try:
        payload = jwt.decode(
            token,
            settings.ADMIN_SESSION_SECRET,
            algorithms=[ADMIN_SESSION_ALGORITHM],
        )
    except JWTError:
        return False
    return payload.get("sub") == "admin"


def set_admin_session_cookie(response, token: str) -> None:
    """写入统一的安全后台会话 Cookie。"""
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=token,
        max_age=settings.ADMIN_SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.ADMIN_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )


def admin_login_is_allowed(request: Request) -> bool:
    """检查当前来源是否超过后台登录失败阈值。"""
    client_host = request.client.host if request.client else "unknown"
    attempts, reset_at = _admin_login_attempts.get(client_host, (0, 0.0))
    if time.monotonic() >= reset_at:
        _admin_login_attempts.pop(client_host, None)
        return True
    return attempts < settings.ADMIN_LOGIN_MAX_ATTEMPTS


def record_admin_login_failure(request: Request) -> None:
    """记录一次后台登录失败。"""
    client_host = request.client.host if request.client else "unknown"
    attempts, reset_at = _admin_login_attempts.get(client_host, (0, 0.0))
    current_time = time.monotonic()
    if current_time >= reset_at:
        attempts = 0
        reset_at = current_time + settings.ADMIN_LOGIN_WINDOW_SECONDS
    _admin_login_attempts[client_host] = (attempts + 1, reset_at)


def clear_admin_login_failures(request: Request) -> None:
    """清理成功登录后的失败计数。"""
    client_host = request.client.host if request.client else "unknown"
    _admin_login_attempts.pop(client_host, None)


def verify_token(
    request: Request, authorization: str | None = Header(default=None)
) -> None:
    if not has_admin_api_access(request, authorization):
        raise HTTPException(status_code=401, detail="未授权")


def require_admin_token(token: str | None) -> None:
    """共享的 admin Token 校验（供各子路由直接调用，缺失→401 / 无效→403）。

    使用 hmac.compare_digest 做定时安全比较，避免按字节比较泄漏 Token。
    """
    if not token:
        raise HTTPException(status_code=401, detail="Missing Token")
    if not is_valid_admin_token(token.replace("Bearer ", "")):
        raise HTTPException(status_code=403, detail="Invalid Token")


def check_login(request: Request) -> bool:
    return is_valid_admin_session(request.cookies.get(ADMIN_SESSION_COOKIE))


def is_allowed_admin_origin(request: Request) -> bool:
    """限制带后台凭证的跨站请求。"""
    origin = request.headers.get("origin", "").strip()
    if not origin:
        return True
    configured = {
        item.strip().rstrip("/")
        for item in settings.ADMIN_ALLOWED_ORIGINS.split(",")
        if item.strip()
    }
    request_origin = f"{request.url.scheme}://{request.url.netloc}".rstrip("/")
    return origin.rstrip("/") in configured or origin.rstrip("/") == request_origin


def has_admin_api_access(request: Request, authorization: str | None) -> bool:
    """优先使用短时 Cookie，兼容 Bearer 仅由显式开关控制。"""
    if not is_allowed_admin_origin(request):
        return False
    if check_login(request):
        return True
    if (
        settings.ADMIN_ALLOW_LEGACY_BEARER
        and authorization
        and authorization.startswith("Bearer ")
    ):
        return is_valid_admin_token(authorization.removeprefix("Bearer "))
    return False


def create_admin_router(
    chat_service: ChatService,
    admin_service: AdminService,
    transfer_mgr: TransferManager,
) -> APIRouter:
    """工厂函数：注入依赖后返回完整路由实例（页面 + API）。"""
    from app.api.admin.dialog import create_dialog_router
    from app.api.admin.transfer import create_transfer_router

    router = APIRouter(tags=["admin"])

    router.include_router(create_dialog_router(chat_service, admin_service))
    router.include_router(
        create_transfer_router(transfer_mgr, admin_service, chat_service)
    )
    return router
