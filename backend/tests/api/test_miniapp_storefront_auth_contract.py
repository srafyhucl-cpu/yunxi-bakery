"""小程序登录到受保护接口的跨路由认证合同测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.miniapp_auth import create_miniapp_auth_router
from app.api.miniapp_orders import create_miniapp_orders_router
from app.repository.config_repo import ConfigRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.channels.storefront import StorefrontAuthService
from app.service.order import OrderApplicationService


@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    """构建同时包含登录和订单保护接口的最小应用。"""
    test_app = FastAPI()
    order_service = OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )
    test_app.include_router(create_miniapp_auth_router(StorefrontAuthService()))
    test_app.include_router(create_miniapp_orders_router(order_service))
    return test_app


@pytest.mark.asyncio
async def test_login_token_can_access_protected_order_api_without_legacy_header(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """登录返回的 token 应能在关闭 legacy 头时访问真实订单接口。"""

    async def fake_request(self: StorefrontAuthService, code: str) -> dict[str, str]:
        assert code == "wx-contract-code"
        return {"openid": "openid_contract"}

    monkeypatch.setattr(StorefrontAuthService, "_request_wechat_session", fake_request)
    monkeypatch.setattr(
        "app.api.channels.storefront._user.settings.STOREFRONT_AUTH_ALLOW_LEGACY_HEADER",
        False,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        login_response = await client.post(
            "/api/v1/miniapp/auth/login",
            json={"code": "wx-contract-code"},
        )
        login_data = login_response.json()["data"]
        protected_response = await client.get(
            "/api/v1/miniapp/orders",
            headers={"Authorization": f"Bearer {login_data['accessToken']}"},
        )
        legacy_response = await client.get(
            "/api/v1/miniapp/orders",
            headers={"x-miniapp-user-id": "wx_openid_contract"},
        )
        missing_response = await client.get("/api/v1/miniapp/orders")

    assert login_response.status_code == 200
    assert login_data["userId"] == "wx_openid_contract"
    assert login_data["tokenType"] == "Bearer"
    assert protected_response.status_code == 200
    assert legacy_response.status_code == 401
    assert missing_response.status_code == 401
