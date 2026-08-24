"""订单未支付超时后台扫描。"""

import asyncio
from collections.abc import Callable
from typing import Any, AsyncContextManager, Protocol

from app.config import settings
from app.logger import setup_logger

logger = setup_logger()


class SupportsOrderTimeoutScan(Protocol):
    """定义未支付超时扫描所需的最小订单服务能力。"""

    async def expire_timeout_unpaid_orders(self) -> dict:
        """扫描并关闭超时未支付订单。"""


class OrderTimeoutScheduler:
    """定时关闭超时未支付订单。"""

    def __init__(
        self,
        order_service: SupportsOrderTimeoutScan,
        scope_factory: Callable[[], AsyncContextManager[object]],
        *,
        interval_seconds: int = settings.MINIAPP_PAYMENT_TIMEOUT_SCAN_INTERVAL_SECONDS,
    ) -> None:
        self._order_service = order_service
        self._scope_factory = scope_factory
        self._interval_seconds = max(interval_seconds, 30)
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> asyncio.Task[None]:
        """启动后台扫描任务。"""
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
                result = await self._order_service.expire_timeout_unpaid_orders()
            expired_count = int(result.get("expiredCount", 0))
            if expired_count > 0:
                logger.info("未支付超时订单已自动关闭: %d", expired_count)
        except Exception as exc:
            logger.error("未支付超时订单扫描失败: %s", exc)


def register_order_timeout_scheduler(
    app: Any,
    order_service: SupportsOrderTimeoutScan,
    bg_tasks: set[asyncio.Task[None]],
    scope_factory: Callable[[], AsyncContextManager[object]],
) -> None:
    """注册订单支付超时扫描任务。"""
    scheduler = OrderTimeoutScheduler(order_service, scope_factory)
    app.state.order_timeout_scheduler = scheduler
    bg_tasks.add(scheduler.start())


async def stop_order_timeout_scheduler(app: Any) -> None:
    """停止订单支付超时扫描任务。"""
    if hasattr(app.state, "order_timeout_scheduler"):
        await app.state.order_timeout_scheduler.stop()


__all__ = [
    "OrderTimeoutScheduler",
    "SupportsOrderTimeoutScan",
    "register_order_timeout_scheduler",
    "stop_order_timeout_scheduler",
]
