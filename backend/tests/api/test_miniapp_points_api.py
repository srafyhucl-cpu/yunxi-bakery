"""小程序积分 API 测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.channels.storefront.points import create_storefront_points_router
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_repo import OrderRepo
from app.repository.points_ledger_repo import PointsLedgerRepo
from app.service.points import PointsService
from tests.helpers.storefront_auth import storefront_auth_headers

MOBILE = "13800000004"
OPENID = "openid_m3_api_001"
USER_ID = f"wx_{OPENID}"


async def _seed_member(db: aiosqlite.Connection, *, points: int = 0) -> None:
    """写入测试会员与可选积分余额。"""
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '积分API测试会员', 'high', 1)",
        (f"cm_{OPENID}", MOBILE),
    )
    await db.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (f"cil_{OPENID}", f"cm_{OPENID}", OPENID, OPENID),
    )
    if points:
        await db.execute(
            "INSERT INTO member_balance (mobile, points) VALUES (?, ?)",
            (MOBILE, points),
        )
    await db.commit()


@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    """构建只包含小程序积分路由的测试应用。"""
    service = PointsService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=PointsLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
        order_repo=OrderRepo(db),
    )
    test_app = FastAPI()
    test_app.include_router(create_storefront_points_router(service))
    return test_app


@pytest.mark.asyncio
async def test_get_points_requires_auth(app: FastAPI) -> None:
    """未带 token 访问积分接口返回 401。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/miniapp/points")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_points_returns_balance(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """已识别会员带 token 查询积分返回余额。"""
    await _seed_member(db, points=2000)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/miniapp/points",
            headers=storefront_auth_headers(USER_ID),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["pointsBalance"] == 2000
    assert payload["data"]["mobile"] == MOBILE


@pytest.mark.asyncio
async def test_points_preview_and_apply_paths(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """积分试算可用；应用抵扣入口被 B3.4 围栏拒绝（等待 D1 预占模型）。"""
    from app.repository.config_repo import ConfigRepo
    from app.repository.order_event_repo import OrderEventRepo
    from app.repository.session_repo import SessionRepo
    from app.repository.youzan_inventory_repo import YouzanInventoryRepo
    from app.repository.youzan_repo import YouzanProductRepo
    from app.service.order import OrderApplicationService

    await _seed_member(db, points=100_000)
    order_service = OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )
    created = await order_service.create_order(
        {
            "items": [
                {
                    "productId": "p_m3_api_001",
                    "title": "M3 API 商品",
                    "priceFen": 10_000,
                    "quantity": 1,
                }
            ],
            "receiverName": "API 测试",
            "receiverPhone": MOBILE,
            "deliveryType": "delivery",
            "deliveryAddress": "API 测试地址",
            "expectTime": "2026-08-20 19:00",
        },
        user_id=USER_ID,
    )
    order_id = created["orderId"]
    headers = storefront_auth_headers(USER_ID)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        preview = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/points-preview", headers=headers
        )
        applied = await client.post(
            f"/api/v1/miniapp/orders/{order_id}/apply-points", headers=headers
        )

    assert preview.status_code == 200
    assert preview.json()["data"]["pointsUsed"] == 5000
    # B3.4 围栏：应用抵扣写入口关闭，试算（只读）不受影响
    assert applied.status_code == 400
    assert "积分抵扣已临时关闭" in applied.json()["detail"]
