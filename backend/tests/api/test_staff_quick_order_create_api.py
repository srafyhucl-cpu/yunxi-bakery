"""店员快捷开单创建 API 测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.staff.auth import create_staff_auth_router
from app.api.staff.quick_order import create_staff_quick_order_router
from app.repository.staff_quick_order_repo import StaffQuickOrderRequestRepo
from app.repository.staff_repo import StaffAuditRepo, StaffRepo
from app.service.staff_auth import StaffAuthService
from app.service.staff_quick_order import (
    MODE_WECHAT_SHARE_CARD,
    StaffQuickOrderService,
)
from tests.helpers.staff_quick_order import (
    balance_fen,
    build_stack,
    create_payload,
    order_count,
    seed_member,
    seed_product,
)


@pytest.fixture(autouse=True)
def isolate_login_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """隔离真实边缘防护库，避免登录测试写入磁盘数据库。"""

    async def allow(_key: str) -> bool:
        return True

    async def noop(_key: str) -> None:
        return None

    monkeypatch.setattr("app.api.staff.auth.attempt_admin_login", allow)
    monkeypatch.setattr("app.api.staff.auth.clear_admin_login_failures", noop)


@pytest.fixture
def auth_service(db: aiosqlite.Connection) -> StaffAuthService:
    return StaffAuthService(
        staff_repo=StaffRepo(db),
        audit_repo=StaffAuditRepo(db),
    )


@pytest.fixture
def quick_order_service(db: aiosqlite.Connection) -> StaffQuickOrderService:
    return build_stack(db)[0]


@pytest.fixture
def app(
    auth_service: StaffAuthService,
    quick_order_service: StaffQuickOrderService,
) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(create_staff_auth_router(auth_service))
    test_app.include_router(
        create_staff_quick_order_router(quick_order_service, auth_service)
    )
    return test_app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


async def _login(client: httpx.AsyncClient, auth_service: StaffAuthService) -> None:
    await auth_service.create_staff("小王", "13800000001", "cashier", "2468")
    response = await client.post(
        "/api/v1/staff/auth/login",
        json={"phone": "13800000001", "pin": "2468"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_requires_staff_login(app: FastAPI) -> None:
    async with _client(app) as client:
        response = await client.post(
            "/api/v1/staff/quick-order/create",
            json=create_payload("req-api-auth-0001"),
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_stored_value_direct_after_login(
    db: aiosqlite.Connection,
    app: FastAPI,
    auth_service: StaffAuthService,
) -> None:
    await seed_member(db, balance_fen=20000)
    await seed_product(db)

    async with _client(app) as client:
        await _login(client, auth_service)
        response = await client.post(
            "/api/v1/staff/quick-order/create",
            json=create_payload("req-api-direct-0001"),
        )
        await db.commit()

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["paymentStatus"] == "paid"
    assert body["data"]["balanceFen"] == 15000
    assert "剩余余额：150.00元" in body["data"]["receiptText"]
    assert await balance_fen(db) == 15000
    assert await order_count(db) == 1


@pytest.mark.asyncio
async def test_repeat_request_id_returns_same_order(
    db: aiosqlite.Connection,
    app: FastAPI,
    auth_service: StaffAuthService,
) -> None:
    await seed_member(db, balance_fen=20000)
    await seed_product(db)

    async with _client(app) as client:
        await _login(client, auth_service)
        first = await client.post(
            "/api/v1/staff/quick-order/create",
            json=create_payload("req-api-replay-0001"),
        )
        await db.commit()
        second = await client.post(
            "/api/v1/staff/quick-order/create",
            json=create_payload("req-api-replay-0001"),
        )
        await db.commit()

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["orderId"] == second.json()["data"]["orderId"]
    assert await order_count(db) == 1
    assert await balance_fen(db) == 15000


@pytest.mark.asyncio
async def test_wechat_share_card_returns_share_path_without_deduction(
    db: aiosqlite.Connection,
    app: FastAPI,
    auth_service: StaffAuthService,
) -> None:
    await seed_member(db, balance_fen=20000)
    await seed_product(db)

    async with _client(app) as client:
        await _login(client, auth_service)
        response = await client.post(
            "/api/v1/staff/quick-order/create",
            json=create_payload(
                "req-api-wechat-0001",
                mode=MODE_WECHAT_SHARE_CARD,
            ),
        )
        await db.commit()

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["paymentStatus"] == "unpaid"
    assert data["sharePath"] == f"/pages/order-detail/index?id={data['orderId']}"
    assert await order_count(db) == 1
    assert await balance_fen(db) == 20000


@pytest.mark.asyncio
async def test_insufficient_balance_returns_400_without_order(
    db: aiosqlite.Connection,
    app: FastAPI,
    auth_service: StaffAuthService,
) -> None:
    await seed_member(db, balance_fen=3000)
    await seed_product(db)

    async with _client(app) as client:
        await _login(client, auth_service)
        response = await client.post(
            "/api/v1/staff/quick-order/create",
            json=create_payload("req-api-insufficient-0001"),
        )
        await db.commit()

    assert response.status_code == 400
    assert "储值余额不足" in response.json()["detail"]
    assert await order_count(db) == 0
    assert await balance_fen(db) == 3000
    request_row = await StaffQuickOrderRequestRepo(db).get("req-api-insufficient-0001")
    assert request_row is not None
    assert request_row["status"] == "failed"
