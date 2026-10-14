"""小程序配送报价 API 测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.channels.storefront.delivery import create_storefront_delivery_router
from app.repository.delivery_quote_repo import DeliveryQuoteRepo
from app.service.delivery.application import DeliveryApplicationService
from app.service.delivery.shansong import ShansongProvider
from tests.helpers.storefront_auth import storefront_auth_headers


@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    """构建只包含配送报价路由的测试应用。"""
    test_app = FastAPI()
    test_app.include_router(
        create_storefront_delivery_router(
            DeliveryApplicationService(ShansongProvider(), DeliveryQuoteRepo(db))
        )
    )
    return test_app


def build_delivery_quote_payload() -> dict:
    return {
        "requestId": "delivery-api-quote",
        "fulfillmentMethod": "beijing_delivery",
        "pickupAddress": "北京市东城区南竹杆胡同2号银河SOHO",
        "receiverName": "配送 API",
        "receiverPhone": "18800000001",
        "receiverAddress": "北京市朝阳区测试路 1 号",
        "expectTime": "2026-09-10 15:00",
        "goodsTotalFen": 19800,
        "items": [{"productId": "p_api_delivery", "quantity": 1}],
    }


@pytest.mark.asyncio
async def test_delivery_quote_api_requires_product_items(app: FastAPI) -> None:
    payload = build_delivery_quote_payload()
    payload.pop("items")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/delivery/quotes",
            json=payload,
            headers=storefront_auth_headers("delivery-api-user"),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "配送报价参数无效"


@pytest.mark.asyncio
async def test_delivery_quote_api_does_not_fabricate_unconfigured_fee(
    app: FastAPI,
) -> None:
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/delivery/quotes",
            json=build_delivery_quote_payload(),
            headers=storefront_auth_headers("delivery-api-user"),
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "provider_unavailable"
    assert data["deliveryFeeFen"] is None


@pytest.mark.asyncio
async def test_delivery_quote_api_rejects_invalid_receiver_phone(
    app: FastAPI,
) -> None:
    """闪送报价不能为非法手机号创建履约快照。"""
    payload = build_delivery_quote_payload()
    payload["receiverPhone"] = "123"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/delivery/quotes",
            json=payload,
            headers=storefront_auth_headers("delivery-invalid-phone-user"),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "请填写正确的 11 位手机号"


@pytest.mark.asyncio
async def test_delivery_quote_api_rejects_insufficient_address(
    app: FastAPI,
) -> None:
    """只有行政区、没有履约细节的地址不能进入闪送报价。"""
    payload = build_delivery_quote_payload()
    payload["receiverAddress"] = "北京市朝阳区"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/delivery/quotes",
            json=payload,
            headers=storefront_auth_headers("delivery-insufficient-address-user"),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "请补充小区、楼栋或门牌号"
