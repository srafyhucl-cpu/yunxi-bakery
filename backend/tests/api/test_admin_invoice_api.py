"""后台发票登记 API 专用测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.admin.invoices import create_admin_invoices_router
from app.config import settings
from app.repository.base import DatabaseHandle
from app.service.invoice.admin import AdminInvoiceService


@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    """构建连接测试数据库的后台发票 API。"""
    test_app = FastAPI()
    test_app.include_router(
        create_admin_invoices_router(AdminInvoiceService(db=DatabaseHandle(db)))
    )
    return test_app


def _admin_headers() -> dict[str, str]:
    """返回现有后台鉴权头。"""
    return {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}


@pytest.mark.asyncio
async def test_invoice_api_requires_admin_token(app: FastAPI) -> None:
    """发票管理接口必须校验后台 Token。"""
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/admin/invoices")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invoice_api_creates_applied_record_and_lists_it(
    app: FastAPI,
) -> None:
    """登记请求应落库为 applied，并可从列表读取。"""
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        created_response = await client.post(
            "/api/v1/admin/invoices",
            headers=_admin_headers(),
            json={
                "orderNo": "ORDER-INV-001",
                "customerName": "测试顾客",
                "companyTitle": "芸熙测试有限公司",
                "taxNo": "91310000TEST001",
                "email": "invoice@example.com",
                "amountFen": 700,
            },
        )
        listed_response = await client.get(
            "/api/v1/admin/invoices",
            headers=_admin_headers(),
        )

    assert created_response.status_code == 200
    created = created_response.json()["data"]
    assert created["status"] == "applied"
    assert created["order_no"] == "ORDER-INV-001"
    assert listed_response.status_code == 200
    assert listed_response.json()["data"][0]["id"] == created["id"]


@pytest.mark.asyncio
async def test_invoice_api_marks_applied_record_issued(app: FastAPI) -> None:
    """已登记请求可标记为 issued，并保存开票备注。"""
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        created_response = await client.post(
            "/api/v1/admin/invoices",
            headers=_admin_headers(),
            json={
                "companyTitle": "芸熙测试有限公司",
                "taxNo": "91310000TEST002",
                "email": "invoice2@example.com",
            },
        )
        invoice_id = created_response.json()["data"]["id"]
        issued_response = await client.post(
            f"/api/v1/admin/invoices/{invoice_id}/mark-issued",
            headers=_admin_headers(),
            json={"issueNote": "电子发票已发送"},
        )

    assert issued_response.status_code == 200
    issued = issued_response.json()["data"]
    assert issued["status"] == "issued"
    assert issued["issue_note"] == "电子发票已发送"


@pytest.mark.xfail(
    strict=True,
    reason="当前实现对 issued 重复标记仍返回 200，待补状态流转阻断",
)
@pytest.mark.asyncio
async def test_invoice_api_rejects_marking_issued_record_again(
    app: FastAPI,
) -> None:
    """已开票请求再次标记应被拒绝，避免非法状态流转。"""
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        created_response = await client.post(
            "/api/v1/admin/invoices",
            headers=_admin_headers(),
            json={
                "companyTitle": "芸熙测试有限公司",
                "taxNo": "91310000TEST003",
                "email": "invoice3@example.com",
            },
        )
        invoice_id = created_response.json()["data"]["id"]
        await client.post(
            f"/api/v1/admin/invoices/{invoice_id}/mark-issued",
            headers=_admin_headers(),
            json={},
        )
        repeated_response = await client.post(
            f"/api/v1/admin/invoices/{invoice_id}/mark-issued",
            headers=_admin_headers(),
            json={},
        )

    assert repeated_response.status_code == 409


@pytest.mark.parametrize("missing_field", ["companyTitle", "taxNo", "email"])
@pytest.mark.xfail(
    strict=True,
    reason="当前请求模型将必填字段缺失归一为空字符串，待补 API 校验",
)
@pytest.mark.asyncio
async def test_invoice_api_rejects_missing_required_field(
    app: FastAPI,
    missing_field: str,
) -> None:
    """企业抬头、税号和邮箱缺失时应拒绝登记。"""
    payload = {
        "companyTitle": "芸熙测试有限公司",
        "taxNo": "91310000TEST004",
        "email": "invoice4@example.com",
    }
    payload.pop(missing_field)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/admin/invoices",
            headers=_admin_headers(),
            json=payload,
        )

    assert response.status_code in {400, 422}
