"""客户群运营 API 测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.admin_customer_groups import create_admin_customer_groups_router
from app.api.miniapp_group_registrations import (
    create_miniapp_group_registrations_router,
)
from app.config import settings
from app.repository.customer_group_repo import CustomerGroupRepo
from app.service.customer import CustomerGroupOperationsService
from tests.helpers.storefront_auth import storefront_auth_headers


@pytest.fixture
def service(db: aiosqlite.Connection) -> CustomerGroupOperationsService:
    """构建客户群运营 API 使用的服务。"""
    return CustomerGroupOperationsService(CustomerGroupRepo(db))


@pytest.fixture
def app(service: CustomerGroupOperationsService) -> FastAPI:
    """构建客户群运营测试应用。"""
    test_app = FastAPI()
    test_app.include_router(create_admin_customer_groups_router(service))
    test_app.include_router(create_miniapp_group_registrations_router(service))
    return test_app


@pytest.mark.asyncio
async def test_customer_group_api_registration_and_summary(
    app: FastAPI,
) -> None:
    """后台建群建批次后，前台可提交登记，后台可读取汇总。"""
    transport = httpx.ASGITransport(app=app)
    admin_headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    miniapp_headers = storefront_auth_headers("group-api-user")

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        group_response = await client.post(
            "/api/v1/admin/customer-groups",
            headers=admin_headers,
            json={
                "chatId": "wr_group_api",
                "name": "接口团购群",
                "ownerUserid": "staff-api",
            },
        )
        campaign_response = await client.post(
            "/api/v1/admin/customer-groups/campaigns",
            headers=admin_headers,
            json={
                "groupId": group_response.json()["data"]["id"],
                "title": "接口团购",
            },
        )
        registration_response = await client.post(
            "/api/v1/miniapp/group-registrations",
            headers=miniapp_headers,
            json={
                "campaignId": campaign_response.json()["data"]["id"],
                "customerName": "接口客户",
                "customerPhone": "18800000011",
                "productName": "草莓奶油蛋糕",
                "quantity": 3,
                "fulfillmentMethod": "pickup",
            },
        )
        summary_response = await client.get(
            "/api/v1/admin/customer-groups/campaigns/"
            f"{campaign_response.json()['data']['id']}/summary",
            headers=admin_headers,
        )
        mine_response = await client.get(
            "/api/v1/miniapp/group-registrations/me",
            headers=miniapp_headers,
        )

    assert group_response.status_code == 200
    assert campaign_response.status_code == 200
    assert registration_response.status_code == 200
    assert registration_response.json()["data"]["userId"] == "group-api-user"
    summary = summary_response.json()["data"]
    assert summary_response.status_code == 200
    assert summary["totalQuantity"] == 3
    assert summary["productTotals"] == [{"productName": "草莓奶油蛋糕", "quantity": 3}]
    assert "接口团购登记汇总" in summary["summaryText"]
    assert mine_response.json()["data"][0]["productName"] == "草莓奶油蛋糕"


@pytest.mark.asyncio
async def test_customer_group_admin_api_requires_token(app: FastAPI) -> None:
    """后台客户群接口必须校验管理员 Token。"""
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/admin/customer-groups")

    assert response.status_code == 401
