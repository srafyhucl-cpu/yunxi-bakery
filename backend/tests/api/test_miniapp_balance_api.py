"""小程序储值余额 API 测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.channels.storefront.recharges import create_storefront_balance_router
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.service.stored_value import StoredValueService
from app.service.stored_value.member import MemberBalanceService
from tests.helpers.storefront_auth import storefront_auth_headers

MOBILE = "13800000005"
OPENID = "openid_balance_api_001"
USER_ID = f"wx_{OPENID}"


async def _seed_member(db: aiosqlite.Connection, *, balance_fen: int = 0) -> None:
    """写入测试会员与可选储值余额。"""
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '储值API测试会员', 'high', 1)",
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
    if balance_fen:
        await db.execute(
            "INSERT INTO member_balance (mobile, stored_value_fen) VALUES (?, ?)",
            (MOBILE, balance_fen),
        )
    await db.commit()


@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    """构建只包含小程序储值余额路由的测试应用。"""
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    service = StoredValueService(member_service=member_service)
    test_app = FastAPI()
    test_app.include_router(create_storefront_balance_router(service))
    return test_app


@pytest.mark.asyncio
async def test_get_balance_requires_auth(app: FastAPI) -> None:
    """未带 token 访问储值余额接口返回 401。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/miniapp/balance")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_balance_returns_member_balance(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """已识别会员带 token 查询储值余额返回正确金额。"""
    await _seed_member(db, balance_fen=8800)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/miniapp/balance",
            headers=storefront_auth_headers(USER_ID),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["balanceFen"] == 8800
    assert payload["data"]["mobile"] == MOBILE


@pytest.mark.asyncio
async def test_get_balance_unlinked_member_returns_zero(app: FastAPI) -> None:
    """未建档或未关联手机号的微信用户查询余额优雅返回零余额，不抛 400。"""
    unlinked_user_id = "wx_unlinked_new_user_888"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/miniapp/balance",
            headers=storefront_auth_headers(unlinked_user_id),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["balanceFen"] == 0
    assert payload["data"]["ledger"] == []
