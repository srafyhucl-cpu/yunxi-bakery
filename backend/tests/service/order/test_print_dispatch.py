"""已支付订单打印调度测试。"""

import asyncio
import json
from contextlib import asynccontextmanager

import aiosqlite

from app.models.order import Order, OrderStatus
from app.repository.order_repo import OrderRepo
from app.repository.print_dispatch_state_repo import PrintDispatchStateRepo
from app.repository.print_job_repo import PrintJobRepo
from app.service.integrations.printer.mock import MockPrinterGateway
from app.service.order.print_dispatch import (
    OPERATOR,
    OrderPrintDispatchScheduler,
    OrderPrintDispatchService,
)
from app.service.order.print_job_service import PrintJobService

INITIAL_CURSOR = "2026-01-01 00:00:00"
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


def _order(
    order_id: str,
    updated_at: str,
    *,
    payment: dict | None = None,
    status: OrderStatus = OrderStatus.PENDING,
) -> Order:
    """构造一张带完整履约信息的测试订单。"""
    return Order(
        id=order_id,
        session_id="session_dispatch",
        channel="storefront",
        user_id="user_dispatch",
        products=json.dumps([CAKE_ITEM], ensure_ascii=False),
        total_amount=198.0,
        delivery=json.dumps(DELIVERY, ensure_ascii=False),
        payment=json.dumps(
            payment or {"status": "paid", "method": "mock"},
            ensure_ascii=False,
        ),
        status=status,
        created_at=updated_at,
        updated_at=updated_at,
    )


async def _create_order(db: aiosqlite.Connection, order: Order) -> None:
    """先补齐订单外键所需会话，再写入测试订单。"""
    await db.execute(
        "INSERT OR IGNORE INTO sessions (id, channel, user_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            order.session_id,
            order.channel,
            order.user_id,
            order.created_at,
            order.updated_at,
        ),
    )
    await OrderRepo(db).create_order(order)


def _print_service(db: aiosqlite.Connection) -> PrintJobService:
    gateway = MockPrinterGateway()
    return PrintJobService(
        PrintJobRepo(db),
        gateway,
        provider_name=gateway.name,
    )


def _dispatch_service(
    db: aiosqlite.Connection,
    print_service=None,
) -> tuple[OrderPrintDispatchService, PrintDispatchStateRepo, PrintJobRepo]:
    state_repo = PrintDispatchStateRepo(db)
    job_repo = PrintJobRepo(db)
    service = OrderPrintDispatchService(
        OrderRepo(db),
        print_service or _print_service(db),
        state_repo,
    )
    return service, state_repo, job_repo


async def test_paid_orders_are_scanned_and_enqueued(
    db: aiosqlite.Connection,
) -> None:
    """mock/余额/微信已支付订单都会入队 PENDING 作业。"""
    service, state_repo, job_repo = _dispatch_service(db)
    await state_repo.get_or_create(INITIAL_CURSOR)
    await _create_order(
        db,
        _order(
            "order_mock",
            "2026-10-19 10:00:00",
            payment={"status": "paid", "method": "mock"},
        ),
    )
    await _create_order(
        db,
        _order(
            "order_balance",
            "2026-10-19 10:01:00",
            payment={"status": "paid", "method": "balance"},
        ),
    )
    await _create_order(
        db,
        _order(
            "order_wechat",
            "2026-10-19 10:02:00",
            payment={"status": "paid", "method": "wechat"},
        ),
    )

    result = await service.dispatch_once()

    assert result["scanned"] == 3
    assert result["enqueued"] == 3
    assert result["skipped"] == 0
    assert result["failed"] == 0
    assert result["lastOrderId"] == "order_wechat"
    for order_id in ("order_mock", "order_balance", "order_wechat"):
        jobs = await job_repo.list_for_order(order_id)
        assert len(jobs) == 1
        assert jobs[0].status == "PENDING"
        assert jobs[0].operator == OPERATOR


async def test_unpaid_orders_are_not_enqueued(db: aiosqlite.Connection) -> None:
    """未支付订单不会被扫描，也不会创建打印作业。"""
    service, state_repo, job_repo = _dispatch_service(db)
    await state_repo.get_or_create(INITIAL_CURSOR)
    await _create_order(
        db,
        _order(
            "order_unpaid",
            "2026-10-19 10:00:00",
            payment={"status": "unpaid", "method": ""},
        ),
    )

    result = await service.dispatch_once()

    assert result["scanned"] == 0
    assert result["enqueued"] == 0
    assert await job_repo.list_for_order("order_unpaid") == []


async def test_refund_terminal_orders_are_not_enqueued(
    db: aiosqlite.Connection,
) -> None:
    """全额/超额退款订单即使支付状态为 paid 也不入队。"""
    service, state_repo, job_repo = _dispatch_service(db)
    await state_repo.get_or_create(INITIAL_CURSOR)
    await _create_order(
        db,
        _order(
            "order_refund_full",
            "2026-10-19 10:00:00",
            payment={"status": "paid", "method": "wechat", "refundStatus": "full"},
        ),
    )
    await _create_order(
        db,
        _order(
            "order_refund_over",
            "2026-10-19 10:01:00",
            payment={"status": "paid", "method": "wechat", "refundStatus": "over"},
        ),
    )

    result = await service.dispatch_once()

    assert result["scanned"] == 0
    assert result["enqueued"] == 0
    assert await job_repo.list_for_order("order_refund_full") == []
    assert await job_repo.list_for_order("order_refund_over") == []


async def test_repeated_dispatch_does_not_duplicate_jobs(
    db: aiosqlite.Connection,
) -> None:
    """同一订单重复调度只保留一条作业。"""
    service, state_repo, job_repo = _dispatch_service(db)
    await state_repo.get_or_create(INITIAL_CURSOR)
    await _create_order(db, _order("order_repeat", "2026-10-19 10:00:00"))

    first = await service.dispatch_once()
    assert first["enqueued"] == 1
    second = await service.dispatch_once()
    # 同一秒游标会重复扫描，但幂等入队不会重复建作业。
    assert second["scanned"] == 1
    assert second["enqueued"] == 1
    assert len(await job_repo.list_for_order("order_repeat")) == 1

    # 即使游标被回拨重扫同一订单，幂等键仍阻止重复作业。
    await state_repo.set_cursor(INITIAL_CURSOR, "")
    third = await service.dispatch_once()
    assert third["scanned"] == 1
    assert len(await job_repo.list_for_order("order_repeat")) == 1


async def test_cursor_advance_discovers_new_paid_order(
    db: aiosqlite.Connection,
) -> None:
    """游标推进后，updated_at 更大的新支付订单在下一轮被发现。"""
    service, state_repo, job_repo = _dispatch_service(db)
    await state_repo.get_or_create(INITIAL_CURSOR)
    await _create_order(db, _order("order_first", "2026-10-19 10:00:00"))

    first = await service.dispatch_once()
    assert first["lastOrderId"] == "order_first"

    await _create_order(db, _order("order_second", "2026-10-19 10:05:00"))
    second = await service.dispatch_once()

    # 游标秒内重扫首单，新单同时被发现；首单幂等不重复建作业。
    assert second["scanned"] == 2
    assert second["enqueued"] == 2
    assert second["lastOrderId"] == "order_second"
    assert len(await job_repo.list_for_order("order_first")) == 1
    assert len(await job_repo.list_for_order("order_second")) == 1


async def test_same_second_order_with_smaller_id_is_not_skipped(
    db: aiosqlite.Connection,
) -> None:
    """同秒内 id 字典序更小的新订单不会被游标永久跳过。"""
    service, state_repo, job_repo = _dispatch_service(db)
    await state_repo.get_or_create(INITIAL_CURSOR)
    same_second = "2026-10-20 12:00:00"
    await _create_order(db, _order("mp_z", same_second))

    first = await service.dispatch_once()

    cursor = await state_repo.get_or_create(INITIAL_CURSOR)
    assert first["lastOrderId"] == "mp_z"
    assert cursor["last_updated_at"] == same_second
    assert cursor["last_order_id"] == "mp_z"

    await _create_order(db, _order("mp_a", same_second))
    second = await service.dispatch_once()

    assert second["scanned"] == 2
    assert second["lastOrderId"] == "mp_z"
    assert len(await job_repo.list_for_order("mp_a")) == 1
    assert len(await job_repo.list_for_order("mp_z")) == 1

    await service.dispatch_once()
    assert len(await job_repo.list_for_order("mp_a")) == 1
    assert len(await job_repo.list_for_order("mp_z")) == 1


async def test_cancelled_paid_order_is_not_enqueued(
    db: aiosqlite.Connection,
) -> None:
    """已取消订单即使支付为 paid 且退款未终态也不入队。"""
    service, state_repo, job_repo = _dispatch_service(db)
    await state_repo.get_or_create(INITIAL_CURSOR)
    await _create_order(
        db,
        _order(
            "order_cancelled",
            "2026-10-20 12:00:00",
            payment={"status": "paid", "method": "wechat", "refundStatus": "pending"},
            status=OrderStatus.CANCELLED,
        ),
    )

    result = await service.dispatch_once()

    assert result["scanned"] == 0
    assert result["enqueued"] == 0
    assert await job_repo.list_for_order("order_cancelled") == []


async def test_cancelled_order_is_skipped_by_service_guard(
    db: aiosqlite.Connection,
) -> None:
    """查询若意外返回已取消订单，服务层双保险仍跳过。"""
    state_repo = PrintDispatchStateRepo(db)
    await state_repo.get_or_create(INITIAL_CURSOR)
    cancelled = _order(
        "order_cancelled_guard",
        "2026-10-20 12:00:00",
        payment={"status": "paid", "method": "wechat", "refundStatus": "pending"},
        status=OrderStatus.CANCELLED,
    )

    class StaticOrderRepo:
        async def list_paid_after(self, updated_at: str, order_id: str, limit: int):
            return [cancelled]

    job_repo = PrintJobRepo(db)
    service = OrderPrintDispatchService(
        StaticOrderRepo(),
        _print_service(db),
        state_repo,
    )

    result = await service.dispatch_once()

    assert result["scanned"] == 1
    assert result["skipped"] == 1
    assert result["enqueued"] == 0
    assert await job_repo.list_for_order(cancelled.id) == []


async def test_enqueue_failure_does_not_advance_cursor(
    db: aiosqlite.Connection,
) -> None:
    """单条入队失败时停在原游标，下一轮仍从失败订单重试。"""
    state_repo = PrintDispatchStateRepo(db)
    await state_repo.get_or_create(INITIAL_CURSOR)
    await _create_order(
        db,
        _order("order_failing", "2026-10-19 10:00:00"),
    )

    class FailingPrintService:
        async def enqueue_for_order(self, order: Order, operator: str = "system"):
            raise RuntimeError("打印作业写入失败")

    service = OrderPrintDispatchService(
        OrderRepo(db),
        FailingPrintService(),
        state_repo,
    )

    result = await service.dispatch_once()

    assert result["scanned"] == 1
    assert result["enqueued"] == 0
    assert result["failed"] == 1
    cursor = await state_repo.get_or_create(INITIAL_CURSOR)
    assert cursor["last_updated_at"] == INITIAL_CURSOR
    assert cursor["last_order_id"] == ""


async def test_empty_scan_keeps_cursor_unchanged(
    db: aiosqlite.Connection,
) -> None:
    """没有新订单时不改写游标。"""
    service, state_repo, _job_repo = _dispatch_service(db)
    await state_repo.get_or_create(INITIAL_CURSOR)

    result = await service.dispatch_once()

    assert result["scanned"] == 0
    cursor = await state_repo.get_or_create(INITIAL_CURSOR)
    assert cursor["last_updated_at"] == INITIAL_CURSOR
    assert cursor["last_order_id"] == ""


async def test_scheduler_start_and_stop_smoke() -> None:
    """调度器启动立即执行一轮，停止时取消后台任务。"""
    called = asyncio.Event()

    class FakeDispatchService:
        def __init__(self) -> None:
            self.calls = 0

        async def dispatch_once(self) -> dict:
            self.calls += 1
            called.set()
            return {"enqueued": 0}

    @asynccontextmanager
    async def fake_scope():
        yield object()

    fake_service = FakeDispatchService()
    scheduler = OrderPrintDispatchScheduler(
        fake_service,
        fake_scope,
        interval_seconds=3600,
    )

    task = scheduler.start()
    await asyncio.wait_for(called.wait(), timeout=1)

    assert fake_service.calls == 1
    assert task.done() is False

    await scheduler.stop()
    assert task.done() is True
