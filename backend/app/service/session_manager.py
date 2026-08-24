"""
会话管理服务。

职责：
- 会话生命周期管理（创建、状态变更）
- 滑动窗口上下文构建（截断超出 token 预算的历史消息）
"""

from app.logger import setup_logger
from app.models.message import Message
from app.repository.message_repo import MessageRepo
from app.repository.session_repo import SessionRepo

logger = setup_logger()

# 对话历史 token 预算上限（超过此值则截断最早的消息）
CONVERSATION_TOKEN_BUDGET = 16000


def estimate_tokens(text: str) -> int:
    """
    启发式 token 估算。

    中文字符约 2 token，ASCII 字符约 0.25 token。
    不需要精确值，只需相对大小用于滑动窗口裁切。
    """
    chinese = sum(1 for c in text if "一" <= c <= "鿿")
    ascii_chars = len(text) - chinese
    return chinese * 2 + ascii_chars // 4 + 8


class SessionManager:
    """会话管理器：获取会话、构建 LLM 上下文。"""

    def __init__(self, session_repo: SessionRepo, message_repo: MessageRepo) -> None:
        self._session_repo = session_repo
        self._message_repo = message_repo

    async def build_context(
        self, session_id: str, budget: int = CONVERSATION_TOKEN_BUDGET
    ) -> list[dict]:
        """
        构建 LLM 上下文（带滑动窗口）。

        从最新消息往前遍历，累计 token 数不超过 budget。
        被截断的历史会插入一条系统提示告知 LLM。
        """
        all_messages = await self._message_repo.get_by_session(session_id)
        if not all_messages:
            return []

        selected: list[Message] = []
        total_tokens = 0

        for msg in reversed(all_messages):
            tokens = msg.estimated_tokens or estimate_tokens(msg.content)
            if total_tokens + tokens > budget:
                break
            selected.append(msg)
            total_tokens += tokens

        selected.reverse()

        result: list[dict] = []
        trimmed = len(all_messages) - len(selected)
        if trimmed > 0:
            result.append(
                {
                    "role": "system",
                    "content": f"(以下为最近 {len(selected)} 条消息之外的 "
                    f"{trimmed} 条历史已被截断)",
                }
            )

        result.extend({"role": msg.role, "content": msg.content} for msg in selected)
        return result
