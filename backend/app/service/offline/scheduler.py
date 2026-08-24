"""离线质检调度器。"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from collections.abc import Callable
from typing import AsyncContextManager, Protocol

from app.config import settings
from app.logger import setup_logger
from app.service.offline.orchestrator import OfflineReviewOrchestrator

logger = setup_logger()


class SupportsIdleSessionClose(Protocol):
    """定义离线沉淀前置会话收口能力。"""

    async def close_once(self) -> int:
        """执行一次空闲会话收口。"""


@dataclass
class OfflineReviewRunSummary:
    """一轮离线质检的运行摘要。"""

    started_at: str = ""
    finished_at: str = ""
    ran: bool = False
    skipped_reason: str = ""
    review_count: int = 0
    gap_count: int = 0
    profile_count: int = 0
    total_processed: int = 0


class OfflineReviewScheduler:
    """以固定间隔触发离线 Agent 编排器。"""

    def __init__(
        self,
        orchestrator: OfflineReviewOrchestrator,
        interval_hours: float,
        scope_factory: Callable[[], AsyncContextManager[object]] | None = None,
        idle_closer: SupportsIdleSessionClose | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._interval_seconds = max(interval_hours, 0.01) * 3600
        self._scope_factory = scope_factory
        self._idle_closer = idle_closer
        self._task: asyncio.Task[None] | None = None
        self._last_summary = OfflineReviewRunSummary()

    def start(self) -> asyncio.Task[None]:
        """启动后台调度任务，并返回任务强引用。"""
        if self._task is not None and not self._task.done():
            logger.warning("离线质检调度器已在运行，跳过重复启动")
            return self._task
        self._task = asyncio.create_task(self._loop())
        logger.info("离线质检调度器已启动 interval_seconds=%s", self._interval_seconds)
        return self._task

    def get_last_summary(self) -> OfflineReviewRunSummary:
        """获取最近一轮运行摘要。"""
        return self._last_summary

    async def stop(self) -> None:
        """停止后台调度任务。"""
        if self._task is None or self._task.done():
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("离线质检调度器已停止")

    async def _loop(self) -> None:
        while True:
            try:
                self._last_summary = await self._run_once()
            except Exception as exc:
                logger.error("离线质检调度轮次失败 err=%s", exc)
            await asyncio.sleep(self._interval_seconds)

    async def _run_once(self) -> OfflineReviewRunSummary:
        started_at = _now_str()
        if not _is_night_window(
            settings.OFFLINE_REVIEW_NIGHT_START_HOUR,
            settings.OFFLINE_REVIEW_NIGHT_END_HOUR,
        ):
            summary = OfflineReviewRunSummary(
                started_at=started_at,
                finished_at=_now_str(),
                ran=False,
                skipped_reason="outside_night_window",
            )
            logger.info("离线质检调度跳过 reason=%s", summary.skipped_reason)
            return summary

        if self._scope_factory is not None:
            async with self._scope_factory():
                await self._close_idle_sessions()
                reviews, gaps, profiles = await self._run_orchestrator()
        else:
            await self._close_idle_sessions()
            reviews, gaps, profiles = await self._run_orchestrator()

        summary = OfflineReviewRunSummary(
            started_at=started_at,
            finished_at=_now_str(),
            ran=True,
            review_count=len(reviews),
            gap_count=len(gaps),
            profile_count=len(profiles),
            total_processed=len(reviews) + len(gaps) + len(profiles),
        )
        logger.info(
            "离线质检调度完成 review_count=%s gap_count=%s profile_count=%s total_processed=%s",
            summary.review_count,
            summary.gap_count,
            summary.profile_count,
            summary.total_processed,
        )
        return summary

    async def _run_orchestrator(self) -> tuple[list, list, list]:
        reviews = await self._orchestrator.run_once()
        gap_agent = getattr(self._orchestrator, "_knowledge_gap_agent", None)
        memory_agent = getattr(self._orchestrator, "_memory_agent", None)
        gaps = getattr(gap_agent, "last_run_result", []) if gap_agent else []
        profiles = getattr(memory_agent, "last_run_result", []) if memory_agent else []
        return reviews, gaps, profiles

    async def _close_idle_sessions(self) -> None:
        if self._idle_closer is None:
            return
        await self._idle_closer.close_once()


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _is_night_window(
    start_hour: int,
    end_hour: int,
    now_hour: int | None = None,
) -> bool:
    current_hour = datetime.now().hour if now_hour is None else now_hour
    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= current_hour < end_hour
    return current_hour >= start_hour or current_hour < end_hour
