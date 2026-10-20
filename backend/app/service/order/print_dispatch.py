"""已支付订单打印调度。

以持久化游标扫描已支付订单，保证 mock/余额/组合/微信通知/查询恢复等
所有支付路径最终都会幂等入队打印作业；应用重启后从上次游标继续。
"""

import asyncio
from collections.abc import Callable
from typing import Any, AsyncContextManager, Protocol

from app.config import settings
from app.logger import setup_logger
from app.models.order import Order, OrderStatus
from app.repository.order_repo import OrderRepo
from app.repository.print_dispatch_state_repo import PrintDispatchStateRepo
from app.service.order.payment_state import loads_payment, status_value
from app.service.order.print_job_service import PrintJobService
from app.utils import now_str

logger = setup_logger()

OPERATOR = "system:print_dispatch"
REFUND_TERMINAL_STATUSES = ("full", "over")


class SupportsPrintEnqueue(Protocol):
    """调度器所需的最小打印入队能力。"""

    async def enqueue_for_order(
        self,
        order: Order,
        operator: str = "system",
    ) -> list[dict]:
        """按订单幂等入队打印作业。"""


class OrderPrintDispatchService:
    """扫描已支付订单并幂等入队打印作业。"""

    def __init__(
        self,
        order_repo: OrderRepo,
        print_job_service: SupportsPrintEnqueue,
        state_repo: PrintDispatchStateRepo,
        batch_size: int = 200,
    ) -> None:
        self._order_repo = order_repo
        self._print_job_service = print_job_service
        self._state_repo = state_repo
        self._batch_size = max(int(batch_size), 1)

    async def dispatch_once(self) -> dict:
        """扫描一批已支付订单；单条失败时不越过该订单推进游标。"""
        cursor = await self._state_repo.get_or_create(now_str())
        orders = await self._order_repo.list_paid_after(
            str(cursor["last_updated_at"]),
            str(cursor["last_order_id"]),
            self._batch_size,
        )
        summary: dict[str, object] = {
            "scanned": len(orders),
            "enqueued": 0,
            "skipped": 0,
            "failed": 0,
            "lastOrderId": str(cursor["last_order_id"]),
        }
        if not orders:
            return summary

        for order in orders:
            if self._is_skipped(order):
                summary["skipped"] = int(summary["skipped"]) + 1
                continue
            try:
                await self._print_job_service.enqueue_for_order(
                    order,
                    operator=OPERATOR,
                )
            except Exception as exc:
                # 失败时不推进游标，下一轮从原时间点重新扫描，避免漏单。
                summary["failed"] = int(summary["failed"]) + 1
                logger.error(
                    "打印调度入队失败 order_id=%s updated_at=%s: %s",
                    order.id,
                    order.updated_at,
                    exc,
                    exc_info=True,
                )
                return summary
            summary["enqueued"] = int(summary["enqueued"]) + 1

        # 同秒内订单会重复扫描，靠入队幂等兜底；游标只推进到时间，不用 id 过滤。
        last = orders[-1]
        await self._state_repo.set_cursor(last.updated_at, last.id)
        summary["lastOrderId"] = last.id
        return summary

    @staticmethod
    def _is_skipped(order: Order) -> bool:
        """已取消或退款终态订单不再打印，避免取消/退款后仍出制作联。"""
        if status_value(order) == OrderStatus.CANCELLED.value:
            return True
        payment = loads_payment(order.payment)
        return str(payment.get("refundStatus", "")) in REFUND_TERMINAL_STATUSES


class OrderPrintDispatchScheduler:
    """定时执行已支付订单打印调度。"""

    def __init__(
        self,
        dispatch_service: OrderPrintDispatchService,
        scope_factory: Callable[[], AsyncContextManager[object]],
        *,
        interval_seconds: float = settings.PRINT_DISPATCH_INTERVAL_SECONDS,
    ) -> None:
        self._dispatch_service = dispatch_service
        self._scope_factory = scope_factory
        self._interval_seconds = max(float(interval_seconds), 0.1)
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> asyncio.Task[None]:
        """启动后台扫描任务，立即返回不阻塞 lifespan。"""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return self._task

    async def stop(self) -> None:
        """停止后台扫描任务。"""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            await self._scan_once()
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                continue

    async def _scan_once(self) -> None:
        try:
            async with self._scope_factory():
                result = await self._dispatch_service.dispatch_once()
            enqueued = int(result.get("enqueued", 0))
            if enqueued > 0:
                logger.info("已支付订单打印作业已入队: %d", enqueued)
        except Exception as exc:
            logger.error("已支付订单打印调度失败: %s", exc, exc_info=True)


def register_print_dispatch_scheduler(
    app: Any,
    order_repo: OrderRepo,
    print_job_service: PrintJobService,
    state_repo: PrintDispatchStateRepo,
    bg_tasks: set[asyncio.Task[None]],
    scope_factory: Callable[[], AsyncContextManager[object]],
    *,
    enabled: bool | None = None,
    interval_seconds: float | None = None,
    batch_size: int | None = None,
) -> None:
    """注册已支付订单打印调度任务；关闭时不创建后台任务。"""
    resolved_enabled = (
        settings.PRINT_DISPATCH_ENABLED if enabled is None else bool(enabled)
    )
    if not resolved_enabled:
        logger.info("打印调度已关闭，不启动后台任务")
        return
    resolved_interval = (
        settings.PRINT_DISPATCH_INTERVAL_SECONDS
        if interval_seconds is None
        else interval_seconds
    )
    resolved_batch = (
        settings.PRINT_DISPATCH_BATCH_SIZE if batch_size is None else batch_size
    )
    dispatch_service = OrderPrintDispatchService(
        order_repo,
        print_job_service,
        state_repo,
        batch_size=resolved_batch,
    )
    scheduler = OrderPrintDispatchScheduler(
        dispatch_service,
        scope_factory,
        interval_seconds=resolved_interval,
    )
    app.state.print_dispatch_scheduler = scheduler
    bg_tasks.add(scheduler.start())


async def stop_print_dispatch_scheduler(app: Any) -> None:
    """停止已支付订单打印调度任务。"""
    if hasattr(app.state, "print_dispatch_scheduler"):
        await app.state.print_dispatch_scheduler.stop()


__all__ = [
    "OPERATOR",
    "OrderPrintDispatchScheduler",
    "OrderPrintDispatchService",
    "SupportsPrintEnqueue",
    "register_print_dispatch_scheduler",
    "stop_print_dispatch_scheduler",
]
