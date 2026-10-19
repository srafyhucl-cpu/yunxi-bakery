"""打印作业服务测试。"""

import json

import aiosqlite

from app.models.order import Order
from app.models.print_job import PrintResult
from app.repository.print_job_repo import PrintJobRepo
from app.service.integrations.printer.mock import MockPrinterGateway
from app.service.order.print_job_service import PrintJobService

CAKE_ITEM = {
    "product_id": 101,
    "title": "草莓定制蛋糕",
    "price_fen": 19800,
    "quantity": 1,
    "fulfillment_type": "PREORDER_CAKE",
    "customization": {
        "size": "8寸",
        "filling": "草莓奶油",
        "greeting": "生日快乐",
        "accessories": "餐具+蜡烛",
    },
}
DAILY_ITEM = {
    "product_id": 201,
    "title": "现烤可颂",
    "price_fen": 1500,
    "quantity": 1,
    "fulfillment_type": "DAILY_READY",
}
DELIVERY = {
    "receiverName": "张三",
    "receiverPhone": "13800000000",
    "fulfillmentMethod": "pickup",
    "expectTime": "2026-10-20 15:00",
}


def _order(products: list[dict]) -> Order:
    return Order(
        id="order_print_service_001",
        session_id="session_001",
        channel="storefront",
        user_id="user_001",
        products=json.dumps(products, ensure_ascii=False),
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


class FailingGateway:
    """固定失败的网关，用于验证重试状态机。"""

    name = "failing"

    async def submit(self, ticket, printer_id):
        return PrintResult(success=False, status="FAILED", error="打印机离线")


async def test_mock_gateway_marks_mocked_with_snapshot(
    db: aiosqlite.Connection,
) -> None:
    """Mock 成功只写 MOCKED，快照有内容且尝试次数为 1。"""
    service = _service(db, MockPrinterGateway())

    jobs = await service.enqueue_for_order(_order([CAKE_ITEM]))
    result = await service.process_job(jobs[0]["id"])

    assert result["success"] is True
    assert result["status"] == "MOCKED"
    assert result["attempts"] == 1
    stored = await PrintJobRepo(db).get_job(jobs[0]["id"])
    assert stored is not None
    assert stored.status == "MOCKED"
    assert stored.attempts == 1
    assert stored.provider_job_id.startswith("mock-")
    assert "生日快乐" in stored.payload_snapshot


async def test_gateway_failure_retries_then_fails(db: aiosqlite.Connection) -> None:
    """失败未达上限回 PENDING，达到上限写 FAILED 并保留错误。"""
    repo = PrintJobRepo(db)
    service = _service(db, FailingGateway(), max_attempts=2)
    job = (await service.enqueue_for_order(_order([CAKE_ITEM])))[0]

    first = await service.process_job(job["id"])
    assert first["status"] == "PENDING"
    stored = await repo.get_job(job["id"])
    assert stored is not None
    assert stored.attempts == 1
    assert "打印机离线" in stored.last_error

    second = await service.process_job(job["id"])
    assert second["status"] == "FAILED"
    stored = await repo.get_job(job["id"])
    assert stored is not None
    assert stored.attempts == 2
    assert stored.last_error == "打印机离线"


async def test_repeat_enqueue_does_not_create_duplicate(
    db: aiosqlite.Connection,
) -> None:
    """重复入队复用原作业，不产生重复联单。"""
    service = _service(db, MockPrinterGateway())
    order = _order([CAKE_ITEM])

    first = await service.enqueue_for_order(order)
    second = await service.enqueue_for_order(order)

    assert first[0]["created"] is True
    assert second[0]["created"] is False
    assert first[0]["id"] == second[0]["id"]
    assert len(await service.list_for_order(order.id)) == 1


async def test_reprint_creates_new_job_and_keeps_original(
    db: aiosqlite.Connection,
) -> None:
    """补打新建 PENDING 作业，原作业保持 MOCKED。"""
    repo = PrintJobRepo(db)
    service = _service(db, MockPrinterGateway())
    job = (await service.enqueue_for_order(_order([CAKE_ITEM])))[0]
    await service.process_job(job["id"])

    reprint = await service.reprint(job["orderId"], "CAKE_KITCHEN", "店员小王")

    assert reprint["id"] != job["id"]
    assert reprint["status"] == "PENDING"
    assert reprint["operator"] == "店员小王"
    assert ":reprint:" in reprint["idempotencyKey"]
    original = await repo.get_job(job["id"])
    assert original is not None
    assert original.status == "MOCKED"


async def test_process_pending_counts_mocked_batch(
    db: aiosqlite.Connection,
) -> None:
    """批量处理混合订单的两张联单并分别计数。"""
    service = _service(db, MockPrinterGateway())
    await service.enqueue_for_order(_order([CAKE_ITEM, DAILY_ITEM]))

    summary = await service.process_pending(limit=10)

    assert summary == {"success": 2, "failed": 0, "mocked": 2, "submitted": 0}
