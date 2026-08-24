"""前台渠道用户标识校验。"""

from contextvars import ContextVar, Token

from fastapi import HTTPException, Request

from app.config import settings
from app.service.channels.storefront.auth import StorefrontAuthService

_current_storefront_user_id: ContextVar[str | None] = ContextVar(
    "current_storefront_user_id", default=None
)


async def authenticate_storefront_request(request: Request):
    """从 Bearer token 建立当前请求的服务端用户上下文。"""
    authorization = request.headers.get("authorization", "")
    user_id = ""
    if authorization.lower().startswith("bearer "):
        try:
            user_id = StorefrontAuthService().verify_access_token(
                authorization[7:].strip()
            )
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
    elif settings.STOREFRONT_AUTH_ALLOW_LEGACY_HEADER:
        user_id = request.headers.get("x-miniapp-user-id", "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录或会话未就绪，请先重新登录")

    token: Token[str | None] = _current_storefront_user_id.set(user_id)
    try:
        yield user_id
    finally:
        _current_storefront_user_id.reset(token)


def require_storefront_user_id(value: str | None) -> str:
    """要求请求显式携带已登录的小程序用户标识。"""
    authenticated_user_id = _current_storefront_user_id.get()
    if authenticated_user_id:
        supplied_user_id = (value or "").strip()
        if supplied_user_id and supplied_user_id != authenticated_user_id:
            raise HTTPException(status_code=403, detail="请求身份与登录会话不一致")
        return authenticated_user_id
    user_id = (
        (value or "").strip() if settings.STOREFRONT_AUTH_ALLOW_LEGACY_HEADER else ""
    )
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录或会话未就绪，请先重新登录")
    return user_id
