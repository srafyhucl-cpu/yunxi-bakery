"""管理后台券 API 测试。"""

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin.coupons import create_admin_coupons_router
from app.config import settings
from app.models.coupon import CouponType
from app.service.coupon.admin import AdminCouponService


@pytest.fixture
def client(db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """构建带真实后台鉴权的券管理 API 测试客户端。"""
    monkeypatch.setattr(settings, "COUPON_AUTHORITY", "local")
    service = AdminCouponService(db=db)
    app = FastAPI()
    app.include_router(create_admin_coupons_router(service))
    return TestClient(app)


def _admin_headers() -> dict[str, str]:
    """后台接口鉴权头（与现有 admin 测试一致）。"""
    return {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}


def test_create_and_list_template(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/admin/coupons/templates",
        headers=_admin_headers(),
        json={
            "name": "满50减10",
            "couponType": CouponType.FULL_REDUCTION,
            "thresholdFen": 5000,
            "valueFen": 1000,
            "validFrom": "2026-08-01",
            "validUntil": "2026-12-31",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    template_id = data["id"]
    assert template_id
    listed = client.get("/api/v1/admin/coupons/templates", headers=_admin_headers())
    assert listed.status_code == 200
    assert len(listed.json()["data"]["templates"]) == 1


def test_grant_coupon_local(client: TestClient) -> None:
    created = client.post(
        "/api/v1/admin/coupons/templates",
        headers=_admin_headers(),
        json={
            "name": "无门槛5元",
            "couponType": CouponType.NO_THRESHOLD,
            "valueFen": 500,
        },
    ).json()["data"]
    resp = client.post(
        "/api/v1/admin/coupons/grants",
        headers=_admin_headers(),
        json={"templateId": created["id"], "mobile": "13800000006"},
    )
    assert resp.status_code == 200
    grant = resp.json()["data"]
    assert grant["couponCode"]
    records = client.get("/api/v1/admin/coupons/records", headers=_admin_headers())
    assert records.status_code == 200
    assert len(records.json()["data"]["records"]) == 1


def test_set_template_status(client: TestClient) -> None:
    created = client.post(
        "/api/v1/admin/coupons/templates",
        headers=_admin_headers(),
        json={"name": "折扣券", "couponType": CouponType.DISCOUNT, "discountBp": 9000},
    ).json()["data"]
    resp = client.post(
        f"/api/v1/admin/coupons/templates/{created['id']}/status",
        headers=_admin_headers(),
        json={"status": "disabled"},
    )
    assert resp.status_code == 200
    listed = client.get(
        "/api/v1/admin/coupons/templates", headers=_admin_headers()
    ).json()["data"]["templates"]
    assert listed[0]["status"] == "disabled"
