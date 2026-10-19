"""打印作业后台 worker 测试。"""

import asyncio
import json
from contextlib import asynccontextmanager

import aiosqlite

from app.models.order import Order
from app.models.print_job import PrintResult
from app.repository.print_job_repo import PrintJobRepo
from app.service.integrations.printer.mock import MockPrinterGateway
from app.service.order.print_job_service import PrintJobService
from app.service.order.print_worker import PrintJobWorker

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


class FailingGateway:
    """固定失败的网关，用于验证 worker 不伪造成功。"""

    name = "failing"

    async def submit(self, ticket, printer_id):
        return PrintResult(success=False, status="FAILED", error="打印机离线")


def _order() -> Order:
    return Order(
        id="order_print_worker_001",
        session_id="session_worker",
        channel="storefront",
        user_id="user_worker",
        products=json.dumps([CAKE_ITEM], ensure_ascii=False),
        total_amount=198.0,
        delivery=json.dumps(DELIVERY, ensure_ascii=False),
        payment=json.dumps({"status": "paid"}),
        created_at="2026-10-19 10:00:00",
        updated_at="2026-10-19 10:00:00",
    )


def _service(
    db: aiosqlite.Connection,
    gateway,
    *,
    max_attempts: int = 3,
) -> PrintJobService:
    return PrintJobService(
        PrintJobRepo(db),
        gateway,
        provider_name=gateway.name,
        max_attempts=max_attempts,
    )


@asynccontextmanager
async def _scope():
    yield object()


def _worker(
    service: PrintJobService,
    *,
    interval_seconds: float = 3600,
    batch_size: int = 20,
) -> PrintJobWorker:
    return PrintJobWorker(
        service,
        _scope,
        interval_seconds=interval_seconds,
        batch_size=batch_size,
    )


async def test_worker_processes_pending_to_mocked(
    db: aiosqlite.Connection,
) -> None:
    """Mock 网关下 worker 只把 PENDING 推进到 MOCKED。"""
    service = _service(db, MockPrinterGateway())
    job = (await service.enqueue_for_order(_order()))[0]
    worker = _worker(service)

    summary = await worker.run_once()

    stored = await PrintJobRepo(db).get_job(job["id"])
    assert stored is not None
    assert stored.status == "MOCKED"
    assert stored.printed_at == ""
    assert summary == {"success": 1, "failed": 0, "mocked": 1, "submitted": 0}


async def test_worker_gateway_failure_retries_until_failed(
    db: aiosqlite.Connection,
) -> None:
    """网关持续失败时先回 PENDING，达到上限后写 FAILED。"""
    service = _service(db, FailingGateway(), max_attempts=2)
    job = (await service.enqueue_for_order(_order()))[0]
    worker = _worker(service)

    first = await worker.run_once()
    stored = await PrintJobRepo(db).get_job(job["id"])
    assert first["failed"] == 1
    assert stored is not None
    assert stored.status == "PENDING"
    assert stored.attempts == 1

    second = await worker.run_once()
    stored = await PrintJobRepo(db).get_job(job["id"])
    assert second["failed"] == 1
    assert stored is not None
    assert stored.status == "FAILED"
    assert stored.attempts == 2
    assert "打印机离线" in stored.last_error


async def test_worker_start_and_stop_consumes_pending(
    db: aiosqlite.Connection,
) -> None:
    """start 后自动消费待打印作业，stop 后后台任务结束。"""
    service = _service(db, MockPrinterGateway())
    job = (await service.enqueue_for_order(_order()))[0]
    worker = _worker(service, interval_seconds=0.1)
    repo = PrintJobRepo(db)

    task = worker.start()

    async def _wait_mocked() -> None:
        while True:
            stored = await repo.get_job(job["id"])
            if stored is not None and stored.status == "MOCKED":
                return
            await asyncio.sleep(0.02)

    await asyncio.wait_for(_wait_mocked(), timeout=3)
    assert task.done() is False

    await worker.stop()
    assert task.done() is True
