"""后台打印队列 API 测试。"""

import json

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.admin.print_jobs import create_admin_print_jobs_router
from app.config import settings
from app.models.order import Order
from app.repository.print_job_repo import PrintJobRepo
from app.service.integrations.printer.mock import MockPrinterGateway
from app.service.order.print_job_service import PrintJobService

CAKE_ITEM = {
    "product_id": 101,
    "title": "草莓定制蛋糕",
    "price_fen": 19800,
    "quantity": 1,
    "fulfillment_type": "PREORDER_CAKE",
}
DELIVERY = {
    "receiverName": "张三",
    "receiverPhone": "13800000000",
    "fulfillmentMethod": "pickup",
    "expectTime": "2026-10-20 15:00",
}


def _order(order_id: str = "order_print_api_001") -> Order:
    return Order(
        id=order_id,
        session_id="session_print_api",
        channel="storefront",
        user_id="user_print_api",
        products=json.dumps([CAKE_ITEM], ensure_ascii=False),
        total_amount=198.0,
        delivery=json.dumps(DELIVERY, ensure_ascii=False),
        payment=json.dumps({"status": "paid"}),
        created_at="2026-10-19 10:00:00",
        updated_at="2026-10-19 10:00:00",
    )


@pytest.fixture
def repo(db: aiosqlite.Connection) -> PrintJobRepo:
    return PrintJobRepo(db)


@pytest.fixture
def service(repo: PrintJobRepo) -> PrintJobService:
    gateway = MockPrinterGateway()
    return PrintJobService(repo, gateway, provider_name=gateway.name)


@pytest.fixture
def app(service: PrintJobService) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(create_admin_print_jobs_router(service))
    return test_app


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


async def _enqueue(
    service: PrintJobService,
    order_id: str = "order_print_api_001",
) -> dict:
    jobs = await service.enqueue_for_order(_order(order_id))
    return jobs[0]


@pytest.mark.asyncio
async def test_print_jobs_list_requires_auth(
    app: FastAPI,
    service: PrintJobService,
) -> None:
    """未携带后台凭证时拒绝访问。"""
    await _enqueue(service)
    async with _client(app) as client:
        response = await client.get("/api/v1/admin/print-jobs")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_print_jobs_list_returns_metadata_without_payload(
    app: FastAPI,
    service: PrintJobService,
) -> None:
    """列表返回元数据，不携带完整小票快照。"""
    job = await _enqueue(service)
    async with _client(app) as client:
        response = await client.get("/api/v1/admin/print-jobs", headers=_headers())

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["id"] for item in items] == [job["id"]]
    assert "payloadSnapshot" not in items[0]
    assert "contentPreview" in items[0]
    assert items[0]["contentPreview"]


@pytest.mark.asyncio
async def test_process_pending_marks_mocked(
    app: FastAPI,
    service: PrintJobService,
    repo: PrintJobRepo,
) -> None:
    """手动触发消费后 Mock 作业为 MOCKED，绝不为 PRINTED。"""
    job = await _enqueue(service)
    async with _client(app) as client:
        response = await client.post(
            "/api/v1/admin/print-jobs/process-pending",
            headers=_headers(),
        )

    assert response.status_code == 200
    assert response.json()["data"]["mocked"] == 1
    stored = await repo.get_job(job["id"])
    assert stored is not None
    assert stored.status == "MOCKED"
    assert stored.printed_at == ""


@pytest.mark.asyncio
async def test_retry_pending_and_failed_jobs(
    app: FastAPI,
    service: PrintJobService,
    repo: PrintJobRepo,
) -> None:
    """PENDING/FAILED 可重试为 MOCKED，已结束作业拒绝重试。"""
    pending = await _enqueue(service, "order_retry_pending")
    failed = await _enqueue(service, "order_retry_failed")
    await repo.mark_failed(failed["id"], "打印机离线", attempts_delta=1)

    async with _client(app) as client:
        pending_response = await client.post(
            f"/api/v1/admin/print-jobs/{pending['id']}/retry",
            headers=_headers(),
        )
        failed_response = await client.post(
            f"/api/v1/admin/print-jobs/{failed['id']}/retry",
            headers=_headers(),
        )
        repeated_response = await client.post(
            f"/api/v1/admin/print-jobs/{pending['id']}/retry",
            headers=_headers(),
        )
        missing_response = await client.post(
            "/api/v1/admin/print-jobs/print_missing/retry",
            headers=_headers(),
        )

    assert pending_response.json()["data"]["status"] == "MOCKED"
    assert failed_response.json()["data"]["status"] == "MOCKED"
    assert repeated_response.status_code == 400
    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_mark_printed_only_for_accepted_jobs(
    app: FastAPI,
    service: PrintJobService,
    repo: PrintJobRepo,
) -> None:
    """仅 SUBMITTED/MOCKED 可人工确认出纸。"""
    pending = await _enqueue(service, "order_mark_pending")
    mocked = await _enqueue(service, "order_mark_mocked")
    submitted = await _enqueue(service, "order_mark_submitted")
    await service.process_job(mocked["id"])
    await repo.mark_result(submitted["id"], "SUBMITTED", "feie-1", "", 1)

    async with _client(app) as client:
        pending_response = await client.post(
            f"/api/v1/admin/print-jobs/{pending['id']}/mark-printed",
            headers=_headers(),
        )
        mocked_response = await client.post(
            f"/api/v1/admin/print-jobs/{mocked['id']}/mark-printed",
            headers=_headers(),
        )
        submitted_response = await client.post(
            f"/api/v1/admin/print-jobs/{submitted['id']}/mark-printed",
            headers=_headers(),
        )

    assert pending_response.status_code == 400
    assert mocked_response.json()["data"]["status"] == "PRINTED"
    assert submitted_response.json()["data"]["status"] == "PRINTED"
    for job in (mocked, submitted):
        stored = await repo.get_job(job["id"])
        assert stored is not None
        assert stored.status == "PRINTED"
        assert stored.printed_at


@pytest.mark.asyncio
async def test_reprint_creates_new_job_and_keeps_original(
    app: FastAPI,
    service: PrintJobService,
    repo: PrintJobRepo,
) -> None:
    """补打新建 PENDING，原作业保持 MOCKED。"""
    job = await _enqueue(service)
    await service.process_job(job["id"])

    async with _client(app) as client:
        response = await client.post(
            f"/api/v1/admin/orders/{job['orderId']}/print-jobs/CAKE_KITCHEN/reprint",
            headers=_headers(),
        )
        missing_response = await client.post(
            "/api/v1/admin/orders/order_missing/print-jobs/CAKE_KITCHEN/reprint",
            headers=_headers(),
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] != job["id"]
    assert data["status"] == "PENDING"
    assert data["operator"].startswith("admin:")
    original = await repo.get_job(job["id"])
    assert original is not None
    assert original.status == "MOCKED"
    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_order_print_jobs_list_returns_metadata(
    app: FastAPI,
    service: PrintJobService,
) -> None:
    """订单维度列表返回全部作业且不含 payloadSnapshot。"""
    job = await _enqueue(service)
    async with _client(app) as client:
        response = await client.get(
            f"/api/v1/admin/orders/{job['orderId']}/print-jobs",
            headers=_headers(),
        )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["id"] for item in items] == [job["id"]]
    assert "payloadSnapshot" not in items[0]


@pytest.mark.asyncio
async def test_list_print_jobs_rejects_invalid_status(
    app: FastAPI,
    service: PrintJobService,
) -> None:
    """非法状态筛选返回 400。"""
    await _enqueue(service)
    async with _client(app) as client:
        response = await client.get(
            "/api/v1/admin/print-jobs",
            params={"status": "UNKNOWN"},
            headers=_headers(),
        )

    assert response.status_code == 400
