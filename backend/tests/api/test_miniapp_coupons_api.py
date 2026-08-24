"""小程序券 API 测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.channels.storefront.coupons import create_storefront_coupons_router
from app.models.coupon import CouponTemplate, CouponType
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.order_repo import OrderRepo
from app.service.coupon import CouponService
from tests.helpers.storefront_auth import storefront_auth_headers

MOBILE = "13800000005"
OPENID = "openid_m4_coupon_api"
USER_ID = f"wx_{OPENID}"


def _build_app(db: aiosqlite.Connection) -> FastAPI:
    service = CouponService(
        template_repo=CouponTemplateRepo(db),
        inventory_repo=CouponInventoryRepo(db),
        customer_repo=CustomerMasterRepo(db),
        order_repo=OrderRepo(db),
    )
    app = FastAPI()
    app.include_router(create_storefront_coupons_router(service))
    return app


@pytest.fixture
def client(db: aiosqlite.Connection) -> TestClient:
    return TestClient(_build_app(db))


@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    """构建只包含小程序券路由的测试应用（httpx.ASGITransport 用）。"""
    return _build_app(db)


def test_coupons_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/miniapp/coupons")
    assert resp.status_code == 401


def test_coupons_returns_error_when_user_not_member(client: TestClient) -> None:
    resp = client.get("/api/v1/miniapp/coupons", headers={"x-miniapp-user-id": USER_ID})
    assert resp.status_code in (400, 401)


async def _seed_member_with_coupon(db: aiosqlite.Connection) -> None:
    """写入测试会员 + 券模板 + TAKE 券行。"""
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '券API测试会员', 'high', 1)",
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
    await CouponTemplateRepo(db).upsert_from_youzan(
        CouponTemplate(
            id="cg_001",
            name="满30减5",
            coupon_type=CouponType.FULL_REDUCTION,
            threshold_fen=3000,
            value_fen=500,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await CouponInventoryRepo(db).insert(
        CouponInventoryEntry(
            coupon_id="c1",
            status=CouponStatus.TAKE,
            mobile=MOBILE,
            coupon_group_id="cg_001",
            title="满30减5",
            value_fen=500,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id="cg_001",
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_get_coupons_includes_threshold_fen(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """已识别会员查询券列表返回模板门槛 thresholdFen。"""
    await _seed_member_with_coupon(db)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/miniapp/coupons",
            headers=storefront_auth_headers(USER_ID),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    coupons = payload["data"]["coupons"]
    assert coupons[0]["couponId"] == "c1"
    assert coupons[0]["thresholdFen"] == 3000


@pytest.mark.asyncio
async def test_get_coupons_threshold_fallback_zero(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """券行有 template_id 但模板缺失时 thresholdFen 返回 0（不抛异常）。"""
    await _seed_member_with_coupon(db)
    await db.execute("DELETE FROM coupon_templates WHERE id = 'cg_001'")
    await db.commit()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/miniapp/coupons",
            headers=storefront_auth_headers(USER_ID),
        )

    assert response.status_code == 200
    coupons = response.json()["data"]["coupons"]
    assert coupons[0]["thresholdFen"] == 0
