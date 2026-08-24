"""小程序订单 API 测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.repository.config_repo import ConfigRepo
from app.api.miniapp_orders import create_miniapp_orders_router
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order import OrderApplicationService
from app.service.channels.storefront import StorefrontAuthService
from tests.helpers.miniapp_catalog_seed import seed_miniapp_product
from tests.helpers.storefront_auth import storefront_auth_headers


@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    """构建只包含小程序订单路由的测试应用。"""
    test_app = FastAPI()
    service = OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )
    test_app.include_router(create_miniapp_orders_router(service))
    return test_app


@pytest.mark.asyncio
async def test_miniapp_order_api_rejects_insufficient_stock(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """小程序下单 API 应把真实商品库存不足转换为 400。"""
    await seed_miniapp_product(
        db,
        item_id=82001,
        title="API 库存不足蛋糕",
        price_fen=19800,
        stock=1,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "82001",
                        "title": "API 库存不足蛋糕",
                        "priceFen": 19800,
                        "quantity": 2,
                    }
                ],
                "receiverName": "库存 API",
                "receiverPhone": "18800000005",
                "expectTime": "2026-06-18 18:00",
            },
            headers=storefront_auth_headers("stock-api-user"),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "商品库存不足: 82001"


@pytest.mark.asyncio
async def test_miniapp_order_api_accepts_server_session_without_legacy_header(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.channels.storefront._user.settings.STOREFRONT_AUTH_ALLOW_LEGACY_HEADER",
        False,
    )
    token = StorefrontAuthService().issue_access_token("wx_secure_order_user")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "secure-order-product",
                        "title": "服务端身份蛋糕",
                        "priceFen": 19800,
                        "quantity": 1,
                    }
                ],
                "expectTime": "2026-06-18 18:00",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"


@pytest.mark.asyncio
async def test_miniapp_order_api_rejects_missing_server_session(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.channels.storefront._user.settings.STOREFRONT_AUTH_ALLOW_LEGACY_HEADER",
        False,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/miniapp/orders")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_miniapp_order_api_creates_order_when_stock_is_enough(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """库存足够时小程序下单 API 应成功，并使用商品宽表价格。"""
    await seed_miniapp_product(
        db,
        item_id=82002,
        title="API 库存充足蛋糕",
        price_fen=22800,
        stock=2,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "82002",
                        "title": "前端传入旧价",
                        "priceFen": 1,
                        "quantity": 2,
                    }
                ],
                "receiverName": "库存 API",
                "receiverPhone": "18800000006",
                "expectTime": "2026-06-18 18:00",
            },
            headers=storefront_auth_headers("stock-api-user"),
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"
    assert response.json()["data"]["totalFen"] == 45600
    row = await YouzanProductRepo(db).get_by_id(82002)
    assert row is not None
    assert row["stock"] == 0


@pytest.mark.asyncio
async def test_miniapp_order_api_detail_returns_timeline(app: FastAPI) -> None:
    """小程序订单详情应返回订单状态时间线。"""
    transport = httpx.ASGITransport(app=app)
    headers = storefront_auth_headers("timeline-api-user")
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        create_response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "p_api_timeline",
                        "title": "API 时间线蛋糕",
                        "priceFen": 19800,
                        "quantity": 1,
                    }
                ],
                "expectTime": "2026-06-18 18:00",
            },
            headers=headers,
        )
        order_id = create_response.json()["data"]["orderId"]
        detail_response = await client.get(
            f"/api/v1/miniapp/orders/{order_id}",
            headers=headers,
        )

    assert detail_response.status_code == 200
    data = detail_response.json()["data"]
    assert [event["status"] for event in data["timeline"]] == ["pending"]
    assert data["timeline"][0]["note"] == "用户提交订单"


@pytest.mark.asyncio
async def test_miniapp_order_api_user_can_cancel_own_pending_order(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """小程序用户可取消自己的待确认订单，并释放真实商品库存。"""
    await seed_miniapp_product(
        db,
        item_id=82003,
        title="API 用户取消蛋糕",
        price_fen=25800,
        stock=1,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        create_response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "82003",
                        "title": "API 用户取消蛋糕",
                        "priceFen": 25800,
                        "quantity": 1,
                    }
                ],
                "receiverName": "取消 API",
                "receiverPhone": "18800000010",
                "expectTime": "2026-06-18 18:00",
            },
            headers=storefront_auth_headers("cancel-api-user"),
        )
        order_id = create_response.json()["data"]["orderId"]
        cancel_response = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/cancel",
            headers=storefront_auth_headers("cancel-api-user"),
        )

    row = await YouzanProductRepo(db).get_by_id(82003)
    assert cancel_response.status_code == 200
    assert cancel_response.json()["data"]["status"] == "cancelled"
    assert row is not None
    assert row["stock"] == 1


@pytest.mark.asyncio
async def test_miniapp_order_api_mock_pay_marks_order_paid(app: FastAPI) -> None:
    """小程序 mock 支付 API 应把自己的订单标记为已支付。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        create_response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "p_api_mock_pay",
                        "title": "API mock 支付蛋糕",
                        "priceFen": 19800,
                        "quantity": 1,
                    }
                ],
                "expectTime": "2026-06-18 18:00",
            },
            headers=storefront_auth_headers("mock-pay-api-user"),
        )
        order_id = create_response.json()["data"]["orderId"]
        pay_response = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/mock-pay",
            headers=storefront_auth_headers("mock-pay-api-user"),
        )

    assert pay_response.status_code == 200
    assert pay_response.json()["data"]["paymentStatus"] == "paid"
    assert pay_response.json()["data"]["paymentMethod"] == "mock"


@pytest.mark.asyncio
async def test_miniapp_order_api_mock_pay_rejects_other_user(app: FastAPI) -> None:
    """小程序用户不能支付其他用户订单。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        create_response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "p_api_mock_pay_owner",
                        "title": "API mock 支付归属蛋糕",
                        "priceFen": 19800,
                        "quantity": 1,
                    }
                ],
                "expectTime": "2026-06-18 18:00",
            },
            headers=storefront_auth_headers("mock-pay-owner-user"),
        )
        order_id = create_response.json()["data"]["orderId"]
        pay_response = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/mock-pay",
            headers=storefront_auth_headers("mock-pay-other-user"),
        )

    assert pay_response.status_code == 404
    assert pay_response.json()["detail"] == "订单不存在"


@pytest.mark.asyncio
async def test_miniapp_order_api_mock_pay_is_disabled_by_default(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.service.order.payment_runtime.settings.ALLOW_MOCK_PAYMENT", False
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        create_response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "disabled-mock-pay",
                        "title": "禁用 mock 支付蛋糕",
                        "priceFen": 19800,
                        "quantity": 1,
                    }
                ],
                "expectTime": "2026-06-18 18:00",
            },
            headers=storefront_auth_headers("disabled-mock-user"),
        )
        order_id = create_response.json()["data"]["orderId"]
        pay_response = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/mock-pay",
            headers=storefront_auth_headers("disabled-mock-user"),
        )

    assert pay_response.status_code == 400
    assert pay_response.json()["detail"] == "生产环境已禁用 mock 支付"


@pytest.mark.asyncio
async def test_miniapp_order_api_prepare_payment_falls_back_to_mock(
    app: FastAPI,
) -> None:
    """小程序支付准备 API 在无微信商户配置时应返回 mock 模式。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        create_response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "p_api_prepare_payment",
                        "title": "API 支付准备蛋糕",
                        "priceFen": 19800,
                        "quantity": 1,
                    }
                ],
                "expectTime": "2026-06-18 18:00",
            },
            headers=storefront_auth_headers("prepare-payment-api-user"),
        )
        order_id = create_response.json()["data"]["orderId"]
        prepare_response = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/prepare-payment",
            headers=storefront_auth_headers("prepare-payment-api-user"),
        )

    assert prepare_response.status_code == 200
    data = prepare_response.json()["data"]
    assert data["mode"] == "mock"
    assert data["paymentMethod"] == "mock"
    assert data["paymentParams"]["action"] == "mock-pay"


@pytest.mark.asyncio
async def test_miniapp_order_api_prepare_payment_rejects_other_user(
    app: FastAPI,
) -> None:
    """小程序用户不能为其他用户订单准备支付。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        create_response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "p_api_prepare_payment_owner",
                        "title": "API 支付归属蛋糕",
                        "priceFen": 19800,
                        "quantity": 1,
                    }
                ],
                "expectTime": "2026-06-18 18:00",
            },
            headers=storefront_auth_headers("prepare-payment-owner-user"),
        )
        order_id = create_response.json()["data"]["orderId"]
        prepare_response = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/prepare-payment",
            headers=storefront_auth_headers("prepare-payment-other-user"),
        )

    assert prepare_response.status_code == 404
    assert prepare_response.json()["detail"] == "订单不存在"


@pytest.mark.asyncio
async def test_miniapp_order_api_user_cannot_cancel_other_users_order(
    app: FastAPI,
) -> None:
    """小程序用户不能取消其他用户订单。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        create_response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "p_cancel_owner",
                        "title": "归属取消测试蛋糕",
                        "priceFen": 19800,
                        "quantity": 1,
                    }
                ],
                "receiverName": "取消 API",
                "receiverPhone": "18800000011",
                "expectTime": "2026-06-18 18:00",
            },
            headers=storefront_auth_headers("cancel-owner-user"),
        )
        order_id = create_response.json()["data"]["orderId"]
        cancel_response = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/cancel",
            headers=storefront_auth_headers("cancel-other-user"),
        )

    assert cancel_response.status_code == 404
    assert cancel_response.json()["detail"] == "订单不存在"


@pytest.mark.asyncio
async def test_miniapp_order_api_rejects_invalid_expect_time(app: FastAPI) -> None:
    """小程序下单 API 应拒绝不可解析的预约时间。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "p_api_invalid_time",
                        "title": "API 时间格式测试蛋糕",
                        "priceFen": 19800,
                        "quantity": 1,
                    }
                ],
                "expectTime": "明天下午",
            },
            headers=storefront_auth_headers("invalid-time-api-user"),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "预约时间格式应为 YYYY-MM-DD HH:mm"


@pytest.mark.asyncio
async def test_miniapp_order_api_rejects_time_outside_business_hours(
    app: FastAPI,
) -> None:
    """小程序下单 API 应拒绝营业时间外的预约时间。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "p_api_closed_time",
                        "title": "API 闭店时间测试蛋糕",
                        "priceFen": 19800,
                        "quantity": 1,
                    }
                ],
                "expectTime": "2026-06-18 08:30",
            },
            headers=storefront_auth_headers("closed-time-api-user"),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "预约时间不在营业时间内"
