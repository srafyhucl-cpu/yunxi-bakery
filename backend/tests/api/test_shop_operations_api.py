"""店铺运营配置 API 测试。"""

import importlib

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.config import settings
from app.repository.config_repo import ConfigRepo
from app.repository.content_change_history_repo import ContentChangeHistoryRepo
from app.repository.knowledge_admin_repo import KnowledgeAdminRepo
from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.message_repo import MessageRepo
from app.repository.session_repo import SessionRepo
from app.repository.transfer_repo import TransferRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.admin import AdminService


@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    """构建只包含店铺配置路由的测试应用。"""
    admin_config = importlib.import_module("app.api.admin_config")
    admin_config = importlib.reload(admin_config)
    admin_service = AdminService(
        session_repo=SessionRepo(db),
        message_repo=MessageRepo(db),
        transfer_repo=TransferRepo(db),
        knowledge_repo=KnowledgeRepo(db),
        config_repo=ConfigRepo(db),
        youzan_product_repo=YouzanProductRepo(db),
        knowledge_product_repo=KnowledgeProductRepo(db),
        knowledge_admin_repo=KnowledgeAdminRepo(db),
        history_repo=ContentChangeHistoryRepo(db),
    )
    test_app = FastAPI()
    test_app.include_router(admin_config.create_shop_config_router(admin_service))
    return test_app


@pytest.mark.asyncio
async def test_admin_shop_operations_update_visible_to_miniapp(app: FastAPI) -> None:
    """后台保存店铺运营配置后，小程序公开配置接口读取到同一份数据。"""
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        initial = await client.get("/api/v1/miniapp/shop-settings")
        assert initial.status_code == 200
        assert initial.json()["data"]["shopName"] == "芸熙烘焙"
        assert initial.json()["data"]["paymentMode"] == "mock"

        payload = {
            "shopName": "芸熙烘焙测试店",
            "customerWechat": "yx-test-wechat",
            "customerPhone": "18800000099",
            "businessHours": "10:00-19:30",
            "pickupAddress": "测试门店自提点",
            "deliveryNotice": "测试配送说明",
            "pickupNotice": "测试自提说明",
            "paymentMode": "wechat",
            "privacyPolicyTitle": "测试隐私政策",
            "privacyPolicyContent": "测试隐私政策内容",
            "userAgreementTitle": "测试用户协议",
            "userAgreementContent": "测试用户协议内容",
            "afterSalesPolicyTitle": "测试售后说明",
            "afterSalesPolicyContent": "测试售后说明内容",
        }
        saved = await client.put(
            "/api/v1/admin/shop-config/operations",
            json=payload,
            headers=headers,
        )
        assert saved.status_code == 200
        assert saved.json()["data"]["shopName"] == "芸熙烘焙测试店"
        assert saved.json()["data"]["customerWechat"] == "yx-test-wechat"
        assert saved.json()["data"]["privacyPolicyTitle"] == "测试隐私政策"
        assert saved.json()["data"]["afterSalesPolicyContent"] == "测试售后说明内容"
        assert saved.json()["data"]["paymentMode"] == "wechat"

        miniapp = await client.get("/api/v1/miniapp/shop-settings")
        assert miniapp.status_code == 200
        assert miniapp.json()["data"]["shopName"] == "芸熙烘焙测试店"
        assert miniapp.json()["data"]["customerPhone"] == "18800000099"
        assert miniapp.json()["data"]["pickupNotice"] == "测试自提说明"
        assert miniapp.json()["data"]["userAgreementTitle"] == "测试用户协议"
        assert miniapp.json()["data"]["privacyPolicyContent"] == "测试隐私政策内容"
        assert miniapp.json()["data"]["paymentMode"] == "wechat"


@pytest.mark.asyncio
async def test_admin_shop_operations_requires_token(app: FastAPI) -> None:
    """后台运营配置接口需要管理员 Token，小程序配置接口公开可读。"""
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        admin_response = await client.get("/api/v1/admin/shop-config/operations")
        assert admin_response.status_code == 401

        miniapp_response = await client.get("/api/v1/miniapp/shop-settings")
        assert miniapp_response.status_code == 200
        assert miniapp_response.json()["data"]["paymentMode"] == "mock"
        assert miniapp_response.json()["data"]["privacyPolicyTitle"] == "隐私政策"
        assert miniapp_response.json()["data"]["userAgreementTitle"] == "用户协议"
        assert miniapp_response.json()["data"]["afterSalesPolicyTitle"] == "售后说明"


@pytest.mark.asyncio
async def test_admin_shop_operations_rejects_invalid_business_hours(
    app: FastAPI,
) -> None:
    """后台运营配置应拒绝不可解析的营业时间。"""
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.put(
            "/api/v1/admin/shop-config/operations",
            json={
                "shopName": "芸熙烘焙测试店",
                "customerWechat": "yx-test-wechat",
                "customerPhone": "18800000099",
                "businessHours": "10点到19点",
                "pickupAddress": "测试门店自提点",
                "deliveryNotice": "测试配送说明",
                "pickupNotice": "测试自提说明",
                "paymentMode": "wechat",
                "privacyPolicyTitle": "测试隐私政策",
                "privacyPolicyContent": "测试隐私政策内容",
                "userAgreementTitle": "测试用户协议",
                "userAgreementContent": "测试用户协议内容",
                "afterSalesPolicyTitle": "测试售后说明",
                "afterSalesPolicyContent": "测试售后说明内容",
            },
            headers=headers,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "营业时间格式应为 HH:mm-HH:mm"


@pytest.mark.asyncio
async def test_admin_shop_operations_keeps_existing_values_when_fields_empty(
    app: FastAPI,
) -> None:
    """后台运营配置保存空字段时应保留旧值。"""
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        await client.put(
            "/api/v1/admin/shop-config/operations",
            json={
                "shopName": "芸熙烘焙测试店",
                "customerWechat": "yx-test-wechat",
                "customerPhone": "18800000099",
                "businessHours": "10:00-19:30",
                "pickupAddress": "测试门店自提点",
                "deliveryNotice": "测试配送说明",
                "pickupNotice": "测试自提说明",
                "paymentMode": "wechat",
                "privacyPolicyTitle": "测试隐私政策",
                "privacyPolicyContent": "测试隐私政策内容",
                "userAgreementTitle": "测试用户协议",
                "userAgreementContent": "测试用户协议内容",
                "afterSalesPolicyTitle": "测试售后说明",
                "afterSalesPolicyContent": "测试售后说明内容",
            },
            headers=headers,
        )
        response = await client.put(
            "/api/v1/admin/shop-config/operations",
            json={
                "shopName": "",
                "customerWechat": "",
                "customerPhone": "",
                "businessHours": "",
                "pickupAddress": "",
                "deliveryNotice": "",
                "pickupNotice": "",
                "paymentMode": "",
                "privacyPolicyTitle": "",
                "privacyPolicyContent": "",
                "userAgreementTitle": "",
                "userAgreementContent": "",
                "afterSalesPolicyTitle": "",
                "afterSalesPolicyContent": "",
            },
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["shopName"] == "芸熙烘焙测试店"
    assert data["businessHours"] == "10:00-19:30"
    assert data["paymentMode"] == "wechat"
    assert data["privacyPolicyTitle"] == "测试隐私政策"
    assert data["userAgreementContent"] == "测试用户协议内容"
