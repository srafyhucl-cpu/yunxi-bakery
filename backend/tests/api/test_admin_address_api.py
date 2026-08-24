"""后台顾客地址 API 测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.admin_addresses import create_admin_addresses_router
from app.config import settings
from app.repository.customer_address_audit_repo import CustomerAddressAuditRepo
from app.repository.customer_address_repo import CustomerAddressRepo
from app.service.customer import CustomerAddressService


@pytest.fixture
def service(db: aiosqlite.Connection) -> CustomerAddressService:
    """构建后台地址 API 使用的真实服务。"""
    return CustomerAddressService(CustomerAddressRepo(db), CustomerAddressAuditRepo(db))


@pytest.fixture
def app(service: CustomerAddressService) -> FastAPI:
    """构建只包含后台地址路由的测试应用。"""
    test_app = FastAPI()
    test_app.include_router(create_admin_addresses_router(service))
    return test_app


@pytest.mark.asyncio
async def test_admin_address_api_requires_token(app: FastAPI) -> None:
    """后台顾客地址接口必须校验管理员 Token。"""
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/admin/addresses")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_address_api_lists_and_searches_addresses(
    app: FastAPI,
    service: CustomerAddressService,
) -> None:
    """后台可按关键词查询顾客地址列表。"""
    await service.save_address(
        {
            "id": "addr-admin-search-1",
            "receiverName": "后台地址一",
            "receiverPhone": "18800000021",
            "address": "银杏路 21 号",
        },
        user_id="admin-address-user-a",
    )
    await service.save_address(
        {
            "id": "addr-admin-search-2",
            "receiverName": "后台地址二",
            "receiverPhone": "18800000022",
            "address": "海棠路 22 号",
        },
        user_id="admin-address-user-b",
    )
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/admin/addresses",
            params={"keyword": "海棠"},
            headers=headers,
        )

    data = response.json()["data"]
    assert response.status_code == 200
    assert data["total"] == 1
    assert data["items"][0]["id"] == "addr-admin-search-2"
    assert data["items"][0]["userId"] == "admin-address-user-b"


@pytest.mark.asyncio
async def test_admin_address_api_creates_address(app: FastAPI) -> None:
    """后台可为指定小程序用户新增收货地址。"""
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        create_response = await client.post(
            "/api/v1/admin/addresses",
            json={
                "userId": "admin-create-user",
                "receiverName": "后台新增",
                "receiverPhone": "18800000031",
                "address": "新增路 31 号",
                "isDefault": True,
            },
            headers=headers,
        )
        list_response = await client.get(
            "/api/v1/admin/addresses",
            params={"keyword": "admin-create-user"},
            headers=headers,
        )
        detail_response = await client.get(
            f"/api/v1/admin/addresses/{create_response.json()['data']['id']}",
            headers=headers,
        )

    created = create_response.json()["data"]
    listed = list_response.json()["data"]["items"][0]
    assert create_response.status_code == 200
    assert created["id"].startswith("addr_")
    assert created["userId"] == "admin-create-user"
    assert created["isDefault"] is True
    assert listed["receiverName"] == "后台新增"
    detail = detail_response.json()["data"]
    assert detail["auditLogs"][0]["action"] == "create"
    assert detail["auditLogs"][0]["operator"].startswith("admin:")


@pytest.mark.asyncio
async def test_admin_address_api_updates_address_and_keeps_single_default(
    app: FastAPI,
    service: CustomerAddressService,
) -> None:
    """后台编辑地址可更新联系人信息，并保持同一用户只有一个默认地址。"""
    await service.save_address(
        {
            "id": "addr-admin-edit-first",
            "receiverName": "后台编辑一",
            "receiverPhone": "18800000032",
            "address": "编辑路 32 号",
            "isDefault": True,
        },
        user_id="admin-edit-user",
    )
    await service.save_address(
        {
            "id": "addr-admin-edit-second",
            "receiverName": "后台编辑二",
            "receiverPhone": "18800000033",
            "address": "编辑路 33 号",
        },
        user_id="admin-edit-user",
    )
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        update_response = await client.put(
            "/api/v1/admin/addresses/addr-admin-edit-second",
            json={
                "userId": "admin-edit-user",
                "receiverName": "后台已编辑",
                "receiverPhone": "18800000034",
                "address": "编辑后路 34 号",
                "isDefault": True,
            },
            headers=headers,
        )
        list_response = await client.get(
            "/api/v1/admin/addresses",
            params={"keyword": "admin-edit-user"},
            headers=headers,
        )
        detail_response = await client.get(
            "/api/v1/admin/addresses/addr-admin-edit-second",
            headers=headers,
        )

    updated = update_response.json()["data"]
    items = list_response.json()["data"]["items"]
    assert update_response.status_code == 200
    assert updated["receiverName"] == "后台已编辑"
    assert updated["receiverPhone"] == "18800000034"
    assert updated["isDefault"] is True
    assert [item["id"] for item in items if item["isDefault"]] == [
        "addr-admin-edit-second"
    ]
    detail = detail_response.json()["data"]
    assert [log["action"] for log in detail["auditLogs"][:2]] == ["update"]


@pytest.mark.asyncio
async def test_admin_address_api_rejects_invalid_payload(app: FastAPI) -> None:
    """后台新增地址时复用小程序地址校验规则。"""
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        missing_user_response = await client.post(
            "/api/v1/admin/addresses",
            json={
                "receiverName": "缺用户",
                "receiverPhone": "18800000035",
                "address": "缺用户路 35 号",
            },
            headers=headers,
        )
        invalid_phone_response = await client.post(
            "/api/v1/admin/addresses",
            json={
                "userId": "admin-invalid-user",
                "receiverName": "手机号错误",
                "receiverPhone": "123",
                "address": "错误路 35 号",
            },
            headers=headers,
        )

    assert missing_user_response.status_code == 400
    assert missing_user_response.json()["detail"] == "请填写用户标识"
    assert invalid_phone_response.status_code == 400
    assert invalid_phone_response.json()["detail"] == "请填写正确的 11 位手机号"


@pytest.mark.asyncio
async def test_admin_address_api_update_missing_address_returns_404(
    app: FastAPI,
) -> None:
    """后台编辑不存在的地址返回 404。"""
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.put(
            "/api/v1/admin/addresses/not-found-address",
            json={
                "userId": "admin-missing-user",
                "receiverName": "不存在",
                "receiverPhone": "18800000036",
                "address": "不存在路 36 号",
            },
            headers=headers,
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "地址不存在"


@pytest.mark.asyncio
async def test_admin_address_api_set_default_and_delete(
    app: FastAPI,
    service: CustomerAddressService,
) -> None:
    """后台可设置默认地址并删除地址，删除默认后自动补默认。"""
    await service.save_address(
        {
            "id": "addr-admin-first",
            "receiverName": "后台默认一",
            "receiverPhone": "18800000023",
            "address": "默认路 23 号",
        },
        user_id="admin-default-user",
    )
    await service.save_address(
        {
            "id": "addr-admin-second",
            "receiverName": "后台默认二",
            "receiverPhone": "18800000024",
            "address": "默认路 24 号",
        },
        user_id="admin-default-user",
    )
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        default_response = await client.post(
            "/api/v1/admin/addresses/addr-admin-second/default",
            headers=headers,
        )
        delete_response = await client.delete(
            "/api/v1/admin/addresses/addr-admin-second",
            headers=headers,
        )
        list_response = await client.get(
            "/api/v1/admin/addresses",
            params={"keyword": "admin-default-user"},
            headers=headers,
        )
        deleted_detail_response = await client.get(
            "/api/v1/admin/addresses/addr-admin-second",
            headers=headers,
        )

    assert default_response.status_code == 200
    assert default_response.json()["data"]["isDefault"] is True
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["id"] == "addr-admin-second"
    assert list_response.json()["data"]["items"][0]["id"] == "addr-admin-first"
    assert list_response.json()["data"]["items"][0]["isDefault"] is True
    assert deleted_detail_response.status_code == 404


@pytest.mark.asyncio
async def test_admin_address_service_records_delete_audit(
    db: aiosqlite.Connection,
) -> None:
    """后台删除地址会留下可追溯的操作审计。"""
    audit_repo = CustomerAddressAuditRepo(db)
    service = CustomerAddressService(CustomerAddressRepo(db), audit_repo)
    await service.save_admin_address(
        {
            "userId": "admin-audit-user",
            "receiverName": "审计删除",
            "receiverPhone": "18800000037",
            "address": "审计路 37 号",
        },
        operator="admin:test",
    )
    created_addresses = await service.list_admin_addresses(keyword="admin-audit-user")
    address_id = created_addresses["items"][0]["id"]
    await service.delete_admin_address(address_id, operator="admin:test")

    logs = await audit_repo.list_by_address(address_id)
    assert [log.action for log in logs[:2]] == ["delete", "create"]
    assert logs[0].operator == "admin:test"
