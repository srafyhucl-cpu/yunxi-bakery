"""客户会话摘要的回复后触发编排。"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.database import db_session_scope
from app.logger import setup_logger
from app.models.conversation_summary import (
    ConversationSummary,
    ConversationSummaryCreate,
)
from app.models.message import Message
from app.models.session import Session, SessionStatus
from app.repository.conversation_summary_repo import ConversationSummaryRepo
from app.repository.message_repo import MessageRepo
from app.service.conversation_summary_service import (
    ConversationSummaryGenerationRequest,
    generate_conversation_summary_draft,
)

logger = setup_logger()

SUMMARY_SOURCE_MESSAGE_LIMIT = 50
MIN_NEW_MESSAGES_FOR_RESUMMARY = 8

SummaryGenerator = Callable[
    [ConversationSummaryGenerationRequest],
    Awaitable[ConversationSummaryCreate | None],
]

_background_summary_tasks: set[asyncio.Task[None]] = set()


@dataclass(frozen=True)
class ConversationSummaryAfterReplyRequest:
    """回复完成后判断是否需要生成会话摘要的输入。"""

    session: Session
    context_budget: dict[str, Any]


def schedule_conversation_summary_after_reply(
    request: ConversationSummaryAfterReplyRequest,
) -> bool:
    """在回复链路完成后排队生成摘要；返回是否真的创建后台任务。"""
    if not _needs_summary_candidate(request.context_budget):
        return False

    task = asyncio.create_task(_run_background_summary_generation(request))
    _background_summary_tasks.add(task)
    task.add_done_callback(_background_summary_tasks.discard)
    return True


async def run_conversation_summary_after_reply(
    request: ConversationSummaryAfterReplyRequest,
    message_repo: MessageRepo,
    summary_repo: ConversationSummaryRepo,
    generator: SummaryGenerator = generate_conversation_summary_draft,
) -> bool:
    """执行一次摘要生成与保存，失败时只返回 False。"""
    if not _needs_summary_candidate(request.context_budget):
        return False
    if _is_human_service_status(request.session.status):
        return False

    try:
        active_summary = await summary_repo.get_active(request.session.id)
        messages = await message_repo.get_by_session(
            request.session.id,
            limit=SUMMARY_SOURCE_MESSAGE_LIMIT,
        )
        if not messages or _has_fresh_active_summary(messages, active_summary):
            return False

        draft = await generator(
            ConversationSummaryGenerationRequest(
                session_id=request.session.id,
                channel=request.session.channel,
                user_id=request.session.user_id,
                messages=messages,
                existing_summary_text=(
                    active_summary.summary_text if active_summary else ""
                ),
            )
        )
        if draft is None:
            return False

        await summary_repo.upsert_active(draft)
        return True
    except Exception as exc:
        logger.warning(
            "回复后会话摘要任务失败 session=%s err=%s", request.session.id, exc
        )
        return False


async def _run_background_summary_generation(
    request: ConversationSummaryAfterReplyRequest,
) -> None:
    async with db_session_scope():
        await run_conversation_summary_after_reply(
            request,
            message_repo=MessageRepo(),
            summary_repo=ConversationSummaryRepo(),
        )


def _needs_summary_candidate(context_budget: dict[str, Any]) -> bool:
    return bool(context_budget.get("needs_session_summary_candidate"))


def _is_human_service_status(status: SessionStatus | str) -> bool:
    return status in (
        SessionStatus.TRANSFER_PENDING,
        SessionStatus.HUMAN_SERVICE,
        SessionStatus.TRANSFER_PENDING.value,
        SessionStatus.HUMAN_SERVICE.value,
    )


def _has_fresh_active_summary(
    messages: list[Message],
    active_summary: ConversationSummary | None,
) -> bool:
    if active_summary is None or not active_summary.source_until_message_id:
        return False

    new_message_count = _count_messages_after(
        messages,
        active_summary.source_until_message_id,
    )
    if new_message_count is None:
        return False
    return new_message_count < MIN_NEW_MESSAGES_FOR_RESUMMARY


def _count_messages_after(messages: list[Message], message_id: str) -> int | None:
    for index, message in enumerate(messages):
        if message.id == message_id:
            return len(messages) - index - 1
    return None
