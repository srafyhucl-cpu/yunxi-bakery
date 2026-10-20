"""打印作业后台消费 worker。

定时把 PENDING 作业交给打印网关：
- Mock 网关只写 MOCKED，飞鹅网关只写 SUBMITTED；
- 任何情况下都不伪造 PRINTED，真实出纸必须由人工确认或打印机回调写入；
- 单轮异常只记录日志，不终止循环，保证后续订单继续打印。
"""

import asyncio
from collections.abc import Callable
from typing import Any, AsyncContextManager

from app.config import settings
from app.logger import setup_logger
from app.service.order.print_job_service import PrintJobService

logger = setup_logger()


class PrintJobWorker:
    """按固定间隔消费待打印作业。"""

    def __init__(
        self,
        print_job_service: PrintJobService,
        scope_factory: Callable[[], AsyncContextManager[object]],
        *,
        interval_seconds: float = settings.PRINT_WORKER_INTERVAL_SECONDS,
        batch_size: int = settings.PRINT_WORKER_BATCH_SIZE,
    ) -> None:
        self._print_job_service = print_job_service
        self._scope_factory = scope_factory
        self._interval_seconds = max(float(interval_seconds), 0.1)
        self._batch_size = max(int(batch_size), 1)
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> asyncio.Task[None]:
        """启动后台任务，立即返回，不阻塞 lifespan。"""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return self._task

    async def stop(self) -> None:
        """停止后台任务；用事件唤醒等待，避免 shutdown 被 sleep 拖住。"""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.debug("打印 worker 已取消")

    async def run_once(self) -> dict:
        """执行一轮消费，供定时循环与测试共用。"""
        async with self._scope_factory():
            summary = await self._print_job_service.process_pending(self._batch_size)
        self._log_summary(summary)
        return summary

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except Exception as exc:
                logger.error("打印 worker 轮次失败: %s", exc, exc_info=True)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                continue

    @staticmethod
    def _log_summary(summary: dict) -> None:
        """记录本轮处理计数；enqueued 表示本轮从待处理队列领取的作业数。"""
        success = int(summary.get("success", 0))
        failed = int(summary.get("failed", 0))
        mocked = int(summary.get("mocked", 0))
        submitted = int(summary.get("submitted", 0))
        enqueued = success + failed
        if enqueued == 0:
            logger.debug("打印 worker 轮次空闲")
            return
        logger.info(
            "打印 worker 轮次完成: enqueued=%d mocked=%d submitted=%d failed=%d",
            enqueued,
            mocked,
            submitted,
            failed,
        )


def register_print_worker(
    app: Any,
    print_job_service: PrintJobService,
    bg_tasks: set[asyncio.Task[None]],
    scope_factory: Callable[[], AsyncContextManager[object]],
    *,
    enabled: bool | None = None,
    interval_seconds: float | None = None,
    batch_size: int | None = None,
) -> None:
    """注册打印消费 worker；关闭时不创建后台任务。"""
    resolved_enabled = (
        settings.PRINT_WORKER_ENABLED if enabled is None else bool(enabled)
    )
    if not resolved_enabled:
        logger.info("打印 worker 已关闭，不启动后台任务")
        return
    resolved_interval = (
        settings.PRINT_WORKER_INTERVAL_SECONDS
        if interval_seconds is None
        else interval_seconds
    )
    resolved_batch = (
        settings.PRINT_WORKER_BATCH_SIZE if batch_size is None else batch_size
    )
    worker = PrintJobWorker(
        print_job_service,
        scope_factory,
        interval_seconds=resolved_interval,
        batch_size=resolved_batch,
    )
    app.state.print_worker = worker
    bg_tasks.add(worker.start())


async def stop_print_worker(app: Any) -> None:
    """停止打印消费 worker。"""
    worker = getattr(app.state, "print_worker", None)
    if worker is not None:
        await worker.stop()


__all__ = ["PrintJobWorker", "register_print_worker", "stop_print_worker"]
