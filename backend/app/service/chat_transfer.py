"""ChatService human handoff boundary."""

from dataclasses import dataclass
from typing import Any

from app.logger import setup_logger
from app.models.session import Session, SessionStatus
from app.models.session_scope import mark_handoff_started
from app.service.transfer_handoff_summary import (
    HandoffSummaryInput,
    build_handoff_note,
    build_handoff_note_with_llm,
)

logger = setup_logger()


@dataclass(frozen=True)
class HumanTransferContext:
    session: Session
    user_id: str
    reason: str
    history_text: str
    transfer_mgr: Any
    session_repo: Any


async def request_human_transfer(context: HumanTransferContext) -> bool:
    """Create a transfer ticket and mark the session as handoff pending."""
    try:
        summary = await build_transfer_summary(context.reason, context.history_text)
        await context.transfer_mgr.request_transfer(
            context.session.id,
            context.user_id,
            reason=context.reason,
            summary=summary,
        )
        await context.session_repo.update_status(
            context.session.id, SessionStatus.TRANSFER_PENDING
        )
        if hasattr(context.session_repo, "update_extra"):
            await context.session_repo.update_extra(
                context.session.id,
                mark_handoff_started(context.session.extra_info),
            )
        return True
    except Exception as exc:
        logger.error(
            "Failed to create human transfer ticket session=%s err=%s",
            context.session.id,
            exc,
        )
        return False


async def build_transfer_summary(reason: str, history_text: str) -> str:
    """Build the concise handoff note saved on the transfer ticket."""
    return await build_handoff_note_with_llm(
        HandoffSummaryInput(reason=reason, history_text=history_text)
    )


def build_transfer_summary_fallback(reason: str, history_text: str) -> str:
    """Build a deterministic handoff note for tests and degraded paths."""
    return build_handoff_note(reason, history_text)
