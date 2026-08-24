"""离线 Agent 编排器。"""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.logger import setup_logger
from app.models.conversation_review import ConversationReview
from app.service.offline.agent_knowledge_gap import KnowledgeGapAgent
from app.service.offline.agent_memory import MemoryAgent
from app.service.offline.agent_qa_review import QaReviewAgent

logger = setup_logger()

ResultT = TypeVar("ResultT")


class OfflineReviewOrchestrator:
    """按顺序调度离线 Agent，并隔离单 Agent 异常。"""

    def __init__(
        self,
        qa_review_agent: QaReviewAgent | None = None,
        knowledge_gap_agent: KnowledgeGapAgent | None = None,
        memory_agent: MemoryAgent | None = None,
    ) -> None:
        self._qa_review_agent = qa_review_agent
        self._knowledge_gap_agent = knowledge_gap_agent
        self._memory_agent = memory_agent

    async def run_once(self) -> list[ConversationReview]:
        """执行一轮离线 Agent 流水线。"""
        reviews = (
            await _safe_run("qa_review", self._qa_review_agent.run)
            if self._qa_review_agent is not None
            else []
        )
        safe_reviews = reviews or []
        if self._knowledge_gap_agent is not None:
            await _safe_run(
                "knowledge_gap",
                lambda: self._knowledge_gap_agent.run(safe_reviews),
            )
        if self._memory_agent is not None:
            await _safe_run("memory", self._memory_agent.run)
        return safe_reviews


async def _safe_run(
    agent_name: str,
    runner: Callable[[], Awaitable[ResultT]],
) -> ResultT | None:
    """捕获单个 Agent 异常，避免拖垮整轮离线任务。"""
    try:
        return await runner()
    except Exception as exc:
        logger.error("离线 Agent 执行失败 agent=%s err=%s", agent_name, exc)
        return None
