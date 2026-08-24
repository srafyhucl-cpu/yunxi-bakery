"""小程序地址簿 API 测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.miniapp_addresses import create_miniapp_addresses_router
from app.repository.customer_address_repo import CustomerAddressRepo
from app.service.customer import CustomerAddressService
from tests.helpers.storefront_auth import storefront_auth_headers


@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    """构建只包含小程序地址路由的测试应用。"""
    test_app = FastAPI()
    service = CustomerAddressService(CustomerAddressRepo(db))
    test_app.include_router(create_miniapp_addresses_router(service))
    return test_app


@pytest.mark.asyncio
async def test_miniapp_address_api_save_list_set_default_and_delete(
    app: FastAPI,
) -> None:
    """小程序地址 API 应支持完整地址簿链路。"""
    transport = httpx.ASGITransport(app=app)
    headers = storefront_auth_headers("address-api-user")

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        first_response = await client.post(
            "/api/v1/miniapp/addresses",
            headers=headers,
            json={
                "id": "addr-api-first",
                "receiverName": "API 一",
                "receiverPhone": "18800000007",
                "address": "API 路 7 号",
            },
        )
        second_response = await client.post(
            "/api/v1/miniapp/addresses",
            headers=headers,
            json={
                "id": "addr-api-second",
                "receiverName": "API 二",
                "receiverPhone": "18800000008",
                "address": "API 路 8 号",
            },
        )
        default_response = await client.post(
            "/api/v1/miniapp/addresses/addr-api-second/default",
            headers=headers,
        )
        list_response = await client.get("/api/v1/miniapp/addresses", headers=headers)
        delete_response = await client.delete(
            "/api/v1/miniapp/addresses/addr-api-second",
            headers=headers,
        )

    assert first_response.status_code == 200
    assert first_response.json()["data"]["isDefault"] is True
    assert second_response.status_code == 200
    assert default_response.status_code == 200
    assert default_response.json()["data"]["id"] == "addr-api-second"
    assert [item["id"] for item in list_response.json()["data"]] == [
        "addr-api-second",
        "addr-api-first",
    ]
    assert delete_response.status_code == 200
    assert delete_response.json()["data"][0]["id"] == "addr-api-first"
    assert delete_response.json()["data"][0]["isDefault"] is True


@pytest.mark.asyncio
async def test_miniapp_address_api_isolates_users(app: FastAPI) -> None:
    """小程序用户不能读取或操作其他用户地址。"""
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        await client.post(
            "/api/v1/miniapp/addresses",
            headers=storefront_auth_headers("address-owner"),
            json={
                "id": "addr-api-owner",
                "receiverName": "归属 API",
                "receiverPhone": "18800000009",
                "address": "归属 API 路",
            },
        )
        other_list = await client.get(
            "/api/v1/miniapp/addresses",
            headers=storefront_auth_headers("address-other"),
        )
        other_default = await client.post(
            "/api/v1/miniapp/addresses/addr-api-owner/default",
            headers=storefront_auth_headers("address-other"),
        )

    assert other_list.status_code == 200
    assert other_list.json()["data"] == []
    assert other_default.status_code == 404


@pytest.mark.asyncio
async def test_miniapp_address_api_rejects_invalid_payload(app: FastAPI) -> None:
    """地址 API 应把校验错误转成 400。"""
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/addresses",
            headers=storefront_auth_headers("address-invalid"),
            json={
                "receiverName": "",
                "receiverPhone": "18800000010",
                "address": "无名路",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "请填写联系人"
