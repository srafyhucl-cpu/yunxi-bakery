"""前台渠道认证服务。"""

import httpx
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings


class StorefrontAuthService:
    """处理微信小程序登录。"""

    async def login(self, code: str) -> dict:
        """使用 wx.login code 换取小程序用户标识；配置缺失时返回明确失败。"""
        normalized_code = code.strip()
        if not normalized_code:
            raise ValueError("登录 code 不能为空")
        if not self._is_wechat_configured():
            raise ValueError("微信小程序 AppID/Secret 未配置，无法换取真实会话")
        payload = await self._request_wechat_session(normalized_code)
        openid = str(payload.get("openid", "")).strip()
        if not openid:
            raise ValueError("微信登录失败，请稍后重试")
        user_id = f"wx_{openid}"
        return {
            "userId": user_id,
            "openid": openid,
            "sessionReady": True,
            "isDemo": False,
            "accessToken": self.issue_access_token(user_id),
            "tokenType": "Bearer",
            "expiresIn": settings.STOREFRONT_AUTH_TTL_SECONDS,
        }

    def issue_access_token(self, user_id: str) -> str:
        """为已完成微信登录的用户签发短期服务端会话 token。"""
        secret = self._require_auth_secret()
        normalized_user_id = user_id.strip()
        if not normalized_user_id:
            raise ValueError("用户身份不能为空")
        issued_at = datetime.now(timezone.utc)
        payload = {
            "sub": normalized_user_id,
            "iat": issued_at,
            "exp": issued_at + timedelta(seconds=settings.STOREFRONT_AUTH_TTL_SECONDS),
        }
        return jwt.encode(payload, secret, algorithm="HS256")

    def verify_access_token(self, access_token: str) -> str:
        """校验服务端会话 token 并返回唯一用户身份。"""
        secret = self._require_auth_secret()
        try:
            payload = jwt.decode(access_token, secret, algorithms=["HS256"])
        except JWTError as exc:
            raise ValueError("登录会话无效或已过期") from exc
        user_id = str(payload.get("sub", "")).strip()
        if not user_id:
            raise ValueError("登录会话缺少用户身份")
        return user_id

    def _require_auth_secret(self) -> str:
        secret = settings.STOREFRONT_AUTH_SECRET.strip()
        if not secret:
            raise ValueError("前台会话密钥未配置")
        return secret

    def _is_wechat_configured(self) -> bool:
        return bool(
            settings.WECHAT_MINIAPP_APP_ID and settings.WECHAT_MINIAPP_APP_SECRET
        )

    async def _request_wechat_session(self, code: str) -> dict:
        try:
            async with httpx.AsyncClient(
                timeout=settings.WECHAT_MINIAPP_HTTP_TIMEOUT_SECONDS
            ) as client:
                response = await client.get(
                    settings.WECHAT_MINIAPP_AUTH_URL,
                    params={
                        "appid": settings.WECHAT_MINIAPP_APP_ID,
                        "secret": settings.WECHAT_MINIAPP_APP_SECRET,
                        "js_code": code,
                        "grant_type": "authorization_code",
                    },
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise ValueError("微信登录上游返回错误") from exc
        except httpx.RequestError as exc:
            raise ValueError("微信登录上游不可用") from exc
        except ValueError as exc:
            raise ValueError("微信登录响应无效") from exc
        return data if isinstance(data, dict) else {}


__all__ = ["StorefrontAuthService"]
