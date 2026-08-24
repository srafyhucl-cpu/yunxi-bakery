"""小程序认证 API 测试。"""

import httpx
import pytest
from fastapi import FastAPI

from app.api.miniapp_auth import create_miniapp_auth_router
from app.service.channels.storefront import StorefrontAuthService


@pytest.mark.asyncio
async def test_miniapp_auth_login_rejects_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未配置微信 AppID/Secret 时应明确失败。"""
    monkeypatch.setattr(
        "app.service.channels.storefront.auth.settings.WECHAT_MINIAPP_APP_ID",
        "",
    )
    monkeypatch.setattr(
        "app.service.channels.storefront.auth.settings.WECHAT_MINIAPP_APP_SECRET",
        "",
    )
    app = FastAPI()
    app.include_router(create_miniapp_auth_router(StorefrontAuthService()))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/auth/login", json={"code": "dev-code"}
        )

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "微信小程序 AppID/Secret 未配置，无法换取真实会话"
    )


@pytest.mark.asyncio
async def test_miniapp_auth_login_rejects_wechat_request_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """微信接口异常时应明确返回失败，不应伪装成登录成功。"""

    async def fake_request(self, code: str) -> dict:
        raise ValueError("微信登录失败: timeout")

    monkeypatch.setattr(
        "app.service.channels.storefront.auth.settings.WECHAT_MINIAPP_APP_ID",
        "wx-app",
    )
    monkeypatch.setattr(
        "app.service.channels.storefront.auth.settings.WECHAT_MINIAPP_APP_SECRET",
        "secret",
    )
    monkeypatch.setattr(
        StorefrontAuthService,
        "_request_wechat_session",
        fake_request,
    )
    app = FastAPI()
    app.include_router(create_miniapp_auth_router(StorefrontAuthService()))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/auth/login", json={"code": "wx-code"}
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "微信登录失败: timeout"


@pytest.mark.asyncio
async def test_miniapp_auth_login_returns_wechat_user_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """配置微信 AppID/Secret 后应按 openid 构造小程序用户 ID。"""

    async def fake_request(self, code: str) -> dict:
        assert code == "wx-code"
        return {"openid": "openid_abc"}

    monkeypatch.setattr(
        "app.service.channels.storefront.auth.settings.WECHAT_MINIAPP_APP_ID",
        "wx-app",
    )
    monkeypatch.setattr(
        "app.service.channels.storefront.auth.settings.WECHAT_MINIAPP_APP_SECRET",
        "secret",
    )
    monkeypatch.setattr(
        StorefrontAuthService,
        "_request_wechat_session",
        fake_request,
    )
    app = FastAPI()
    app.include_router(create_miniapp_auth_router(StorefrontAuthService()))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/auth/login", json={"code": "wx-code"}
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["userId"] == "wx_openid_abc"
    assert data["openid"] == "openid_abc"
    assert data["sessionReady"] is True
    assert data["isDemo"] is False
    assert data["tokenType"] == "Bearer"
    assert data["expiresIn"] == 3600
    assert StorefrontAuthService().verify_access_token(data["accessToken"]) == (
        "wx_openid_abc"
    )


@pytest.mark.asyncio
async def test_miniapp_auth_login_fails_closed_without_session_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_request(self, code: str) -> dict:
        return {"openid": "openid_without_secret"}

    monkeypatch.setattr(
        "app.service.channels.storefront.auth.settings.WECHAT_MINIAPP_APP_ID",
        "wx-app",
    )
    monkeypatch.setattr(
        "app.service.channels.storefront.auth.settings.WECHAT_MINIAPP_APP_SECRET",
        "secret",
    )
    monkeypatch.setattr(
        "app.service.channels.storefront.auth.settings.STOREFRONT_AUTH_SECRET",
        "",
    )
    monkeypatch.setattr(StorefrontAuthService, "_request_wechat_session", fake_request)

    with pytest.raises(ValueError, match="会话密钥未配置"):
        await StorefrontAuthService().login("wx-code")
