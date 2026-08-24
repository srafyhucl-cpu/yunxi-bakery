"""ChatService 的回复后处理与埋点边界。"""

import json
import re
from typing import Any

from app.logger import setup_logger
from app.models.message import Message, MessageRole
from app.models.session import Session
from app.repository.message_repo import MessageRepo
from app.service.llm.intent import IntentType
from app.service.llm.soothe import apply_soothe, needs_soothe
from app.utils import now_str

logger = setup_logger()

MARKDOWN_DECORATION_PATTERN = re.compile(r"(\*\*|__)(.+?)\1")
INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")
HEADING_MARK_PATTERN = re.compile(r"(?m)^#{1,6}\s+")
BLOCKQUOTE_MARK_PATTERN = re.compile(r"(?m)^>\s*")
EXCESSIVE_BLANK_LINES_PATTERN = re.compile(r"\n{3,}")


def postprocess_reply(reply: str | None, user_content: str) -> str | None:
    if not reply:
        return reply

    cleaned_reply = clean_plain_text_reply(reply)
    if needs_soothe(user_content):
        return apply_soothe(cleaned_reply)
    return cleaned_reply


def clean_plain_text_reply(reply: str) -> str:
    """清理纯文本渠道不支持的 Markdown 装饰。"""
    cleaned_reply = MARKDOWN_DECORATION_PATTERN.sub(r"\2", reply)
    cleaned_reply = INLINE_CODE_PATTERN.sub(r"\1", cleaned_reply)
    cleaned_reply = HEADING_MARK_PATTERN.sub("", cleaned_reply)
    cleaned_reply = BLOCKQUOTE_MARK_PATTERN.sub("", cleaned_reply)
    cleaned_reply = cleaned_reply.replace("**", "").replace("__", "")
    cleaned_reply = EXCESSIVE_BLANK_LINES_PATTERN.sub("\n\n", cleaned_reply)
    return cleaned_reply.strip()


async def save_assistant_reply(
    message_repo: MessageRepo,
    session_id: str,
    reply: str | None,
) -> None:
    if not reply:
        return

    assistant_msg = Message(
        id="",
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=reply,
    )
    await message_repo.save(assistant_msg)


async def record_reply_latency(
    analytics_repo: Any,
    session: Session,
    user_id: str,
    channel: str,
    intent: IntentType,
    intent_ms: int,
    timing: dict,
    loop_ms: int,
    total_ms: int,
) -> None:
    try:
        await analytics_repo.add_event(
            session_id=session.id,
            buyer_id=user_id,
            event_type="reply_latency",
            event_source="chat_pipeline",
            ref_id=session.id,
            meta_data=json.dumps(
                {
                    "intent": intent.name,
                    "intent_ms": intent_ms,
                    "rag_ms": timing.get("rag_ms"),
                    "llm_ms": timing.get("llm_ms"),
                    "tool_rounds": timing.get("tool_rounds", 0),
                    "context_budget": timing.get("context_budget", {}),
                    "loop_ms": loop_ms,
                    "total_ms": total_ms,
                    "channel": channel,
                }
            ),
            created_at=now_str(),
        )
    except Exception as exc:
        logger.warning("回复延迟埋点失败: %s", exc)
