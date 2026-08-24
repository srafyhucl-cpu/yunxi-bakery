"""离线质检服务装配入口。"""

import asyncio
from collections.abc import Callable
from typing import AsyncContextManager
from typing import Any

from app.config import settings
from app.service.offline.agent_knowledge_gap import KnowledgeGapAgent
from app.service.offline.agent_memory import MemoryAgent
from app.service.offline.agent_qa_review import QaReviewAgent
from app.service.offline.orchestrator import OfflineReviewOrchestrator
from app.service.offline.scheduler import OfflineReviewScheduler


def register_offline_review_scheduler(
    app: Any,
    repos: dict[str, Any],
    bg_tasks: set[asyncio.Task[None]],
    scope_factory: Callable[[], AsyncContextManager[object]],
    idle_closer: Any | None = None,
) -> None:
    """按配置启动离线质检调度器，并持有后台任务强引用。"""
    if not (
        settings.ENABLE_OFFLINE_QA
        or settings.ENABLE_OFFLINE_KNOWLEDGE_GAP
        or settings.ENABLE_OFFLINE_MEMORY
    ):
        return

    qa_review_agent = (
        QaReviewAgent(
            session_repo=repos["session_repo"],
            message_repo=repos["message_repo"],
            review_repo=repos["conversation_review_repo"],
            max_sessions=settings.OFFLINE_REVIEW_MAX_SESSIONS,
        )
        if settings.ENABLE_OFFLINE_QA
        else None
    )
    knowledge_gap_agent = (
        KnowledgeGapAgent(
            message_repo=repos["message_repo"],
            gap_repo=repos["knowledge_gap_repo"],
            max_reviews=settings.OFFLINE_REVIEW_MAX_SESSIONS,
        )
        if settings.ENABLE_OFFLINE_KNOWLEDGE_GAP
        else None
    )
    memory_agent = (
        MemoryAgent(
            session_repo=repos["offline_session_repo"],
            message_repo=repos["message_repo"],
            profile_repo=repos["customer_profile_repo"],
            max_sessions=settings.OFFLINE_REVIEW_MAX_SESSIONS,
        )
        if settings.ENABLE_OFFLINE_MEMORY
        else None
    )
    orchestrator = OfflineReviewOrchestrator(
        qa_review_agent,
        knowledge_gap_agent,
        memory_agent,
    )
    scheduler = OfflineReviewScheduler(
        orchestrator=orchestrator,
        interval_hours=settings.OFFLINE_REVIEW_INTERVAL_HOURS,
        scope_factory=scope_factory,
        idle_closer=idle_closer,
    )
    app.state.offline_review_scheduler = scheduler
    bg_tasks.add(scheduler.start())


async def stop_offline_review_scheduler(app: Any) -> None:
    """停止离线质检调度器。"""
    if hasattr(app.state, "offline_review_scheduler"):
        await app.state.offline_review_scheduler.stop()
