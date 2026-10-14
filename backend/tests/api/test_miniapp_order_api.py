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
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order import OrderApplicationService
from app.service.channels.storefront import StorefrontAuthService
from tests.helpers.miniapp_catalog_seed import seed_miniapp_product
from tests.helpers.legacy_order_catalog import (
    LegacyOrderInventoryRepo,
    LegacyOrderProductRepo,
)
from tests.helpers.storefront_auth import storefront_auth_headers


@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    """构建只包含小程序订单路由的测试应用。"""
    test_app = FastAPI()
    service = OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=LegacyOrderProductRepo(db),
        inventory_repo=LegacyOrderInventoryRepo(db),
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
                "receiverName": "服务端身份测试",
                "receiverPhone": "18800000012",
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
                "receiverName": "时间线测试",
                "receiverPhone": "18800000013",
                "deliveryType": "pickup",
                "pickupAddress": "北京市东城区南竹杆胡同2号银河SOHO",
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
    assert data["pickupAddress"] == "北京市东城区南竹杆胡同2号银河SOHO"
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
                "receiverName": "mock 支付测试",
                "receiverPhone": "18800000014",
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
                "receiverName": "支付归属测试",
                "receiverPhone": "18800000015",
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
                "receiverName": "禁用 mock 测试",
                "receiverPhone": "18800000016",
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
                "receiverName": "支付准备测试",
                "receiverPhone": "18800000017",
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
async def test_miniapp_order_api_paid_order_prepare_is_idempotent_without_prepay(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已支付订单再次准备支付时只返回已支付快照，不触发微信预下单。"""
    headers = storefront_auth_headers("paid-prepare-payment-api-user")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        create_response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "p_api_paid_prepare_payment",
                        "title": "已支付支付准备蛋糕",
                        "priceFen": 19800,
                        "quantity": 1,
                    }
                ],
                "receiverName": "已支付支付准备测试",
                "receiverPhone": "18800000042",
                "expectTime": "2026-06-18 18:00",
            },
            headers=headers,
        )
        order_id = create_response.json()["data"]["orderId"]
        pay_response = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/mock-pay",
            headers=headers,
        )
        assert pay_response.status_code == 200

        async def fail_prepay(*_args, **_kwargs):
            raise AssertionError("已支付订单不应再次创建微信预下单")

        monkeypatch.setattr(
            "app.service.order.payment_runtime."
            "OrderPaymentRuntimeService._create_wechat_jsapi_prepay",
            fail_prepay,
        )
        prepare_response = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/prepare-payment",
            headers=headers,
        )

    assert prepare_response.status_code == 200
    data = prepare_response.json()["data"]
    assert data["paymentStatus"] == "paid"
    assert data["paymentMethod"] == "mock"
    assert data["paymentParams"] == {}


@pytest.mark.asyncio
async def test_miniapp_order_api_rejects_unknown_numeric_product_without_side_effects(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """未知数字商品应被真实目录拒绝，且不得写订单、库存、事件或支付账本。"""
    user_id = "unknown-numeric-product-api-user"
    headers = storefront_auth_headers(user_id)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "999999998",
                        "title": "客户端伪造商品",
                        "priceFen": 1,
                        "quantity": 1,
                    }
                ],
                "receiverName": "未知商品 API",
                "receiverPhone": "18800000043",
                "deliveryType": "pickup",
                "expectTime": "2026-06-18 18:00",
                "remark": "",
            },
            headers=headers,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "商品不存在: 999999998"
    assert await OrderRepo(db).list_by_user(user_id) == []
    assert await YouzanProductRepo(db).get_by_id(999999998) is None
    counts = await db.execute_fetchall(
        "SELECT (SELECT COUNT(*) FROM orders) AS orders, "
        "(SELECT COUNT(*) FROM order_events) AS order_events, "
        "(SELECT COUNT(*) FROM payment_transactions) AS payment_transactions, "
        "(SELECT COUNT(*) FROM sessions) AS sessions"
    )
    assert dict(counts[0]) == {
        "orders": 0,
        "order_events": 0,
        "payment_transactions": 0,
        "sessions": 0,
    }


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
                "receiverName": "支付归属准备测试",
                "receiverPhone": "18800000018",
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
async def test_miniapp_pickup_order_lifecycle_creates_prepares_mock_pays_and_reads_detail(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """自提订单应完成创建、mock 支付准备、支付和详情读取闭环。"""
    await seed_miniapp_product(
        db,
        item_id=82010,
        title="API 自提闭环蛋糕",
        price_fen=19800,
        stock=2,
    )
    headers = storefront_auth_headers("pickup-lifecycle-api-user")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        create_response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "82010",
                        "title": "API 自提闭环蛋糕",
                        "priceFen": 1,
                        "quantity": 1,
                    }
                ],
                "receiverName": "自提闭环测试",
                "receiverPhone": "18800000020",
                "deliveryType": "pickup",
                "fulfillmentMethod": "pickup",
                "pickupAddress": "北京市东城区南竹杆胡同2号银河SOHO",
                "expectTime": "2026-06-18 18:00",
            },
            headers=headers,
        )
        assert create_response.status_code == 200
        created = create_response.json()["data"]
        order_id = created["orderId"]
        assert created["status"] == "pending"
        assert created["totalFen"] == 19800

        prepare_response = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/prepare-payment",
            headers=headers,
        )
        assert prepare_response.status_code == 200
        prepared = prepare_response.json()["data"]
        assert prepared["mode"] == "mock"
        assert prepared["paymentMethod"] == "mock"
        assert prepared["paymentStatus"] == "unpaid"
        assert prepared["paymentParams"]["action"] == "mock-pay"

        pay_response = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/mock-pay",
            headers=headers,
        )
        assert pay_response.status_code == 200
        paid = pay_response.json()["data"]
        assert paid["paymentStatus"] == "paid"
        assert paid["paymentMethod"] == "mock"

        detail_response = await client.get(
            f"/api/v1/miniapp/orders/{order_id}",
            headers=headers,
        )

    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["id"] == order_id
    assert detail["status"] == "pending"
    assert detail["paymentStatus"] == "paid"
    assert detail["paymentMethod"] == "mock"
    assert detail["deliveryType"] == "pickup"
    assert detail["pickupAddress"] == "北京市东城区南竹杆胡同2号银河SOHO"
    assert detail["items"][0]["product_id"] == "82010"
    assert detail["timeline"]
    assert detail["timeline"][0]["status"] == "pending"


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


@pytest.mark.asyncio
async def test_miniapp_order_api_rejects_missing_receiver_name(
    app: FastAPI,
) -> None:
    """服务端不能接受无法履约联系人的订单。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "p_api_missing_receiver_name",
                        "title": "缺少联系人蛋糕",
                        "priceFen": 19800,
                        "quantity": 1,
                    }
                ],
                "receiverName": " ",
                "receiverPhone": "18800000040",
                "expectTime": "2026-06-18 18:00",
            },
            headers=storefront_auth_headers("missing-receiver-name-user"),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "请填写联系人"


@pytest.mark.asyncio
async def test_miniapp_order_api_rejects_invalid_receiver_phone(
    app: FastAPI,
) -> None:
    """服务端不能把非法手机号固化进订单履约快照。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "p_api_invalid_receiver_phone",
                        "title": "非法手机号蛋糕",
                        "priceFen": 19800,
                        "quantity": 1,
                    }
                ],
                "receiverName": "手机号测试",
                "receiverPhone": "123",
                "expectTime": "2026-06-18 18:00",
            },
            headers=storefront_auth_headers("invalid-receiver-phone-user"),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "请填写正确的 11 位手机号"


@pytest.mark.asyncio
async def test_miniapp_order_api_rejects_beijing_delivery_without_address(
    app: FastAPI,
) -> None:
    """北京闪送下单必须在报价分支前拒绝空配送地址。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/orders",
            json={
                "items": [
                    {
                        "productId": "p_api_missing_delivery_address",
                        "title": "缺少配送地址蛋糕",
                        "priceFen": 19800,
                        "quantity": 1,
                    }
                ],
                "receiverName": "配送测试",
                "receiverPhone": "18800000041",
                "deliveryType": "delivery",
                "fulfillmentMethod": "beijing_delivery",
                "deliveryAddress": "",
                "expectTime": "2026-06-18 18:00",
            },
            headers=storefront_auth_headers("missing-delivery-address-user"),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "请填写配送地址"
