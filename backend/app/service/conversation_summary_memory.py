"""客户会话短期摘要热路径只读加载。"""

from typing import Protocol

from app.logger import setup_logger
from app.models.conversation_summary import ConversationSummary

logger = setup_logger()


class ConversationSummaryReader(Protocol):
    async def get_active(self, session_id: str) -> ConversationSummary | None: ...


async def load_active_conversation_summary_text(
    summary_repo: ConversationSummaryReader | None,
    session_id: str,
) -> str:
    """只读加载当前会话 active 摘要，失败时空摘要降级。"""
    if summary_repo is None:
        return ""

    try:
        active_summary = await summary_repo.get_active(session_id)
    except Exception as exc:
        logger.warning(
            "会话摘要读取失败，空摘要继续: session=%s err=%s", session_id, exc
        )
        return ""

    if active_summary is None:
        return ""
    return active_summary.summary_text.strip()
