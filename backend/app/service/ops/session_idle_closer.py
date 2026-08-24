"""活跃会话空闲自动收口。"""

import asyncio
from collections.abc import Callable
from typing import Any, AsyncContextManager

from app.config import settings
from app.logger import setup_logger
from app.repository.session_repo import SessionRepo

logger = setup_logger()


class SessionIdleCloser:
    """定时关闭超过空闲阈值的活跃会话。"""

    def __init__(
        self,
        session_repo: SessionRepo,
        scope_factory: Callable[[], AsyncContextManager[object]],
        *,
        idle_minutes: int = settings.SESSION_IDLE_CLOSE_MINUTES,
        interval_seconds: int = settings.SESSION_IDLE_CLOSE_SCAN_INTERVAL_SECONDS,
    ) -> None:
        self._session_repo = session_repo
        self._scope_factory = scope_factory
        self._idle_minutes = max(idle_minutes, 1)
        self._interval_seconds = max(interval_seconds, 30)
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> asyncio.Task[None]:
        """启动后台收口任务。"""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return self._task

    async def stop(self) -> None:
        """停止后台收口任务。"""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            await self.close_once()
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                continue

    async def close_once(self) -> int:
        """执行一次空闲会话收口。"""
        try:
            async with self._scope_factory():
                closed_count = await self._session_repo.close_idle_active_sessions(
                    self._idle_minutes
                )
            if closed_count > 0:
                logger.info("空闲活跃会话已自动关闭: %d", closed_count)
            return closed_count
        except Exception as exc:
            logger.error("空闲活跃会话收口失败: %s", exc)
            return 0


def register_session_idle_closer(
    app: Any,
    session_repo: SessionRepo,
    bg_tasks: set[asyncio.Task[None]],
    scope_factory: Callable[[], AsyncContextManager[object]],
) -> None:
    """注册活跃会话空闲收口任务。"""
    closer = SessionIdleCloser(session_repo, scope_factory)
    app.state.session_idle_closer = closer
    bg_tasks.add(closer.start())


async def stop_session_idle_closer(app: Any) -> None:
    """停止活跃会话空闲收口任务。"""
    if hasattr(app.state, "session_idle_closer"):
        await app.state.session_idle_closer.stop()


__all__ = [
    "SessionIdleCloser",
    "register_session_idle_closer",
    "stop_session_idle_closer",
]
