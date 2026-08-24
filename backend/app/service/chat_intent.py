"""ChatService intent detection and recent-history boundary."""

import time
from dataclasses import dataclass

from app.logger import setup_logger
from app.models.session import Session
from app.service.llm.intent import IntentType, detect_intent
from app.service.session_manager import SessionManager

logger = setup_logger()

INTENT_HISTORY_MESSAGES = 4
INTENT_CONTENT_PREVIEW = 80


@dataclass(frozen=True)
class IntentDetectionResult:
    intent: IntentType
    history: list[dict]
    history_text: str
    started_at: float
    finished_at: float
    intent_ms: int


def build_history_text(history: list[dict]) -> str:
    """Render the latest dialog turns for intent detection and handoff notes."""
    return "\n".join(
        f"{'用户' if m.get('role') == 'user' else 'AI'}："
        f"{str(m.get('content', ''))[:INTENT_CONTENT_PREVIEW]}"
        for m in history[-INTENT_HISTORY_MESSAGES:]
        if m.get("role") in ("user", "assistant")
    )


async def detect_intent_with_timing(
    session_mgr: SessionManager,
    session: Session,
    content: str,
) -> IntentDetectionResult:
    """Detect intent and return timing metadata for observability."""
    started_at = time.monotonic()
    history = await session_mgr.build_context(session.id)
    history_text = build_history_text(history)
    intent = await detect_intent(content, history=history_text)
    finished_at = time.monotonic()
    intent_ms = round((finished_at - started_at) * 1000)
    logger.info("会话 %s 意图: %s intent_ms=%d", session.id, intent.name, intent_ms)
    return IntentDetectionResult(
        intent=intent,
        history=history,
        history_text=history_text,
        started_at=started_at,
        finished_at=finished_at,
        intent_ms=intent_ms,
    )
