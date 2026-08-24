"""活跃会话空闲收口调度测试。"""

import asyncio

from app.service.ops.session_idle_closer import SessionIdleCloser


class FakeScope:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeSessionRepo:
    def __init__(self) -> None:
        self.idle_minutes: list[int] = []

    async def close_idle_active_sessions(self, idle_minutes: int) -> int:
        self.idle_minutes.append(idle_minutes)
        return 2


async def test_session_idle_closer_closes_once() -> None:
    """调度器应按配置调用仓库并返回关闭数量。"""
    repo = FakeSessionRepo()
    closer = SessionIdleCloser(
        repo,  # type: ignore[arg-type]
        FakeScope,
        idle_minutes=30,
        interval_seconds=30,
    )

    closed_count = await closer.close_once()

    assert closed_count == 2
    assert repo.idle_minutes == [30]


async def test_session_idle_closer_start_and_stop() -> None:
    """调度器应能启动并优雅停止。"""
    repo = FakeSessionRepo()
    closer = SessionIdleCloser(
        repo,  # type: ignore[arg-type]
        FakeScope,
        idle_minutes=30,
        interval_seconds=30,
    )

    closer.start()
    await asyncio.sleep(0.01)
    await closer.stop()

    assert repo.idle_minutes
