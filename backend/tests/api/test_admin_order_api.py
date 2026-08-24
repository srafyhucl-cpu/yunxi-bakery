"""后台订单 API 测试。"""

import aiosqlite
import httpx
import pytest
import json
from datetime import datetime, timedelta
from fastapi import FastAPI

from app.api.admin_orders import create_admin_orders_router
from app.config import settings
from app.repository.config_repo import ConfigRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order import OrderApplicationService
from app.service.order.payment_state import (
    PAYMENT_TIMEOUT_MINUTES,
    build_initial_payment,
)
from tests.helpers.miniapp_catalog_seed import seed_miniapp_product


@pytest.fixture
def service(db: aiosqlite.Connection) -> OrderApplicationService:
    """构建后台订单 API 使用的真实服务。"""
    return OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )


@pytest.fixture
def app(service: OrderApplicationService) -> FastAPI:
    """构建只包含后台订单路由的测试应用。"""
    test_app = FastAPI()
    test_app.include_router(create_admin_orders_router(service))
    return test_app


@pytest.mark.asyncio
async def test_admin_order_api_expire_unpaid_releases_stock(
    db: aiosqlite.Connection,
    service: OrderApplicationService,
    app: FastAPI,
) -> None:
    """后台关闭未支付订单时应释放真实商品库存。"""
    await seed_miniapp_product(
        db,
        item_id=83001,
        title="后台关闭未支付蛋糕",
        price_fen=19800,
        stock=1,
    )
    created = await service.create_order(
        {
            "items": [
                {
                    "productId": "83001",
                    "title": "后台关闭未支付蛋糕",
                    "priceFen": 19800,
                    "quantity": 1,
                }
            ],
            "expectTime": "2026-06-18 18:00",
        },
        user_id="admin-expire-user",
    )
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            f"/api/v1/admin/orders/{created['orderId']}/expire-unpaid",
            headers=headers,
        )

    row = await YouzanProductRepo(db).get_by_id(83001)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "cancelled"
    assert response.json()["data"]["paymentStatus"] == "expired"
    assert row is not None
    assert row["stock"] == 1


@pytest.mark.asyncio
async def test_admin_order_api_status_update_writes_timeline(
    service: OrderApplicationService,
    app: FastAPI,
) -> None:
    """后台更新订单状态后，订单详情应返回真实状态事件。"""
    created = await service.create_order(
        {
            "items": [
                {
                    "productId": "p_admin_timeline",
                    "title": "后台时间线蛋糕",
                    "priceFen": 19800,
                    "quantity": 1,
                }
            ],
            "expectTime": "2026-06-18 18:00",
        },
        user_id="admin-timeline-user",
    )
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        update_response = await client.post(
            f"/api/v1/admin/orders/{created['orderId']}/status",
            json={"status": "confirmed"},
            headers=headers,
        )
        detail_response = await client.get(
            f"/api/v1/admin/orders/{created['orderId']}",
            headers=headers,
        )

    assert update_response.status_code == 200
    assert detail_response.status_code == 200
    timeline = detail_response.json()["data"]["timeline"]
    assert [event["status"] for event in timeline] == ["pending", "confirmed"]
    assert timeline[1]["operator"] == "admin"


@pytest.mark.asyncio
async def test_admin_order_api_expire_timeout_unpaid_orders(
    db: aiosqlite.Connection,
    service: OrderApplicationService,
    app: FastAPI,
) -> None:
    """后台可手动触发一次超时未支付扫描。"""
    await seed_miniapp_product(
        db,
        item_id=83002,
        title="后台扫描超时蛋糕",
        price_fen=19800,
        stock=1,
    )
    created = await service.create_order(
        {
            "items": [
                {
                    "productId": "83002",
                    "title": "后台扫描超时蛋糕",
                    "priceFen": 19800,
                    "quantity": 1,
                }
            ],
            "expectTime": "2026-06-18 18:00",
        },
        user_id="admin-scan-user",
    )
    old_created_at = (
        datetime.now() - timedelta(minutes=PAYMENT_TIMEOUT_MINUTES + 1)
    ).strftime("%Y-%m-%d %H:%M:%S")
    await OrderRepo(db).update_payment(
        created["orderId"],
        json.dumps(build_initial_payment(old_created_at), ensure_ascii=False),
        old_created_at,
    )

    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/admin/orders/expire-timeout-unpaid", headers=headers
        )

    row = await YouzanProductRepo(db).get_by_id(83002)
    assert response.status_code == 200
    assert response.json()["data"]["expiredCount"] == 1
    assert row is not None
    assert row["stock"] == 1


@pytest.mark.asyncio
async def test_admin_order_summary_and_board_filter(
    service: OrderApplicationService,
    app: FastAPI,
) -> None:
    """后台订单经营看板应使用全量汇总口径，并支持同口径列表筛选。"""
    pending = await service.create_order(
        {
            "items": [
                {
                    "productId": "summary_pending",
                    "title": "汇总待确认蛋糕",
                    "priceFen": 10000,
                    "quantity": 1,
                }
            ],
            "expectTime": "2026-06-18 18:00",
        },
        user_id="summary-pending-user",
    )
    fulfilling = await service.create_order(
        {
            "items": [
                {
                    "productId": "summary_fulfilling",
                    "title": "汇总履约蛋糕",
                    "priceFen": 20000,
                    "quantity": 1,
                }
            ],
            "expectTime": "2026-06-18 18:00",
        },
        user_id="summary-fulfilling-user",
    )
    closed = await service.create_order(
        {
            "items": [
                {
                    "productId": "summary_closed",
                    "title": "汇总关闭蛋糕",
                    "priceFen": 30000,
                    "quantity": 1,
                }
            ],
            "expectTime": "2026-06-18 18:00",
        },
        user_id="summary-closed-user",
    )
    await service.update_admin_order_status(fulfilling["orderId"], "confirmed")
    await service.confirm_mock_payment(
        fulfilling["orderId"],
        user_id="summary-fulfilling-user",
    )
    await service.expire_unpaid_order(closed["orderId"])

    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        summary_response = await client.get(
            "/api/v1/admin/orders/summary", headers=headers
        )
        unpaid_response = await client.get(
            "/api/v1/admin/orders",
            params={"boardFilter": "unpaid"},
            headers=headers,
        )
        fulfilling_response = await client.get(
            "/api/v1/admin/orders",
            params={"boardFilter": "fulfilling"},
            headers=headers,
        )
        closed_response = await client.get(
            "/api/v1/admin/orders",
            params={"boardFilter": "closed"},
            headers=headers,
        )

    assert summary_response.status_code == 200
    cards = {card["key"]: card for card in summary_response.json()["data"]["cards"]}
    assert cards["all"]["count"] == 3
    assert cards["all"]["totalFen"] == 60000
    assert cards["unpaid"]["count"] == 1
    assert cards["unpaid"]["totalFen"] == 10000
    assert cards["pending"]["count"] == 1
    assert cards["fulfilling"]["count"] == 1
    assert cards["closed"]["count"] == 1
    assert summary_response.json()["data"]["totalCount"] == 3
    assert summary_response.json()["data"]["totalFen"] == 60000

    assert unpaid_response.status_code == 200
    assert [item["id"] for item in unpaid_response.json()["data"]["items"]] == [
        pending["orderId"]
    ]
    assert fulfilling_response.status_code == 200
    assert [item["id"] for item in fulfilling_response.json()["data"]["items"]] == [
        fulfilling["orderId"]
    ]
    assert closed_response.status_code == 200
    assert [item["id"] for item in closed_response.json()["data"]["items"]] == [
        closed["orderId"]
    ]
