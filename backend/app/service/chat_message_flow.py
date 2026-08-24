"""用户消息处理主流程边界。"""

from collections.abc import Callable
import time
from dataclasses import dataclass

from app.logger import setup_logger
from app.models.message import Message, MessageRole
from app.models.session import Session, SessionCreate, SessionStatus
from app.repository.analytics_repo import AnalyticsRepo
from app.repository.customer_profile_repo import CustomerProfileRepo
from app.repository.message_repo import MessageRepo
from app.repository.session_repo import SessionRepo
from app.service.chat_ai_loop import (
    AiConversationLoopDependencies,
    AiConversationLoopRequest,
    run_ai_conversation_loop,
)
from app.service.chat_ai_failure import (
    AiFailureAutoTransferContext,
    handle_ai_failure_auto_transfer,
)
from app.service.chat_intent import IntentDetectionResult, detect_intent_with_timing
from app.service.chat_reply import (
    postprocess_reply,
    record_reply_latency,
    save_assistant_reply,
)
from app.service.chat_transfer import HumanTransferContext, request_human_transfer
from app.service.conversation_summary_scheduler import (
    ConversationSummaryAfterReplyRequest,
)
from app.service.customer_memory import load_customer_profile
from app.service.llm.constants import LLM_FAILURE_REASON_KEY
from app.service.llm.intent_types import is_transfer_intent
from app.service.reply_guard import ReplyGuardContext, apply_reply_guard
from app.service.session_manager import SessionManager
from app.service.transfer_manager import TransferManager

logger = setup_logger()

AI_FAILURE_AUTO_TRANSFER_DEFAULT_REASON = "AI 服务降级，自动转人工接手"


@dataclass(frozen=True)
class ChatMessageFlowDependencies:
    session_mgr: SessionManager
    session_repo: SessionRepo
    message_repo: MessageRepo
    transfer_mgr: TransferManager
    analytics_repo: AnalyticsRepo
    ai_loop_dependencies: AiConversationLoopDependencies
    fallback_reply: str
    transfer_reply: str
    auto_transfer_reply: str
    customer_profile_repo: CustomerProfileRepo | None = None
    schedule_conversation_summary: (
        Callable[[ConversationSummaryAfterReplyRequest], bool] | None
    ) = None


@dataclass(frozen=True)
class ChatMessageRequest:
    channel: str
    user_id: str
    content: str
    staff_id: str = ""
    channel_msg_id: str = ""
    image_base64: str | None = None


async def handle_chat_message(
    dependencies: ChatMessageFlowDependencies,
    request: ChatMessageRequest,
) -> str | None:
    if await is_duplicate_message(dependencies.message_repo, request.channel_msg_id):
        logger.debug("消息已处理，跳过: %s", request.channel_msg_id)
        return None

    session = await prepare_session_and_save_user_message(dependencies, request)
    if session is None:
        logger.debug("消息已由其他处理器认领，跳过: %s", request.channel_msg_id)
        return None
    if is_human_service_session(session):
        logger.info("会话 %s 处于人工服务状态，跳过 AI", session.id)
        return None

    intent_result = await detect_intent_with_timing(
        dependencies.session_mgr, session, request.content
    )
    if is_transfer_intent(intent_result.intent):
        return await handle_transfer_intent(
            dependencies=dependencies,
            session=session,
            user_id=request.user_id,
            reason=request.content,
            history_text=intent_result.history_text,
        )

    return await complete_ai_reply(dependencies, request, session, intent_result)


async def is_duplicate_message(
    message_repo: MessageRepo,
    channel_msg_id: str,
) -> bool:
    return bool(channel_msg_id and await message_repo.exists(channel_msg_id))


async def prepare_session_and_save_user_message(
    dependencies: ChatMessageFlowDependencies,
    request: ChatMessageRequest,
) -> Session | None:
    session = await dependencies.session_repo.get_or_create(
        SessionCreate(
            id="",
            channel=request.channel,
            user_id=request.user_id,
            staff_id=request.staff_id,
        ),
    )
    user_msg = Message(
        id="",
        session_id=session.id,
        role=MessageRole.USER,
        content=request.content,
        channel_msg_id=request.channel_msg_id,
    )
    if not await dependencies.message_repo.save_if_new(user_msg):
        return None
    if hasattr(dependencies.session_repo, "touch"):
        await dependencies.session_repo.touch(session.id)
    return session


def is_human_service_session(session: Session) -> bool:
    return session.status in (
        SessionStatus.TRANSFER_PENDING,
        SessionStatus.HUMAN_SERVICE,
    )


async def handle_transfer_intent(
    dependencies: ChatMessageFlowDependencies,
    session: Session,
    user_id: str,
    reason: str,
    history_text: str,
) -> str:
    transfer_created = await request_human_transfer(
        HumanTransferContext(
            session=session,
            user_id=user_id,
            reason=reason,
            history_text=history_text,
            transfer_mgr=dependencies.transfer_mgr,
            session_repo=dependencies.session_repo,
        )
    )
    if not transfer_created:
        return dependencies.fallback_reply

    await save_assistant_reply(
        dependencies.message_repo, session.id, dependencies.transfer_reply
    )
    return dependencies.transfer_reply


async def complete_ai_reply(
    dependencies: ChatMessageFlowDependencies,
    request: ChatMessageRequest,
    session: Session,
    intent_result: IntentDetectionResult,
) -> str | None:
    timing: dict = {}
    reply = await run_ai_reply_loop(
        dependencies=dependencies,
        request=request,
        session=session,
        intent_result=intent_result,
        timing=timing,
    )
    finished_at = time.monotonic()
    loop_ms = round((finished_at - intent_result.finished_at) * 1000)
    total_ms = round((finished_at - intent_result.started_at) * 1000)
    failure_reason = get_ai_failure_reason(timing)
    if failure_reason:
        reply = await handle_ai_failure_auto_transfer(
            build_ai_failure_auto_transfer_context(
                dependencies,
                request,
                session,
                intent_result.history_text,
                failure_reason,
            )
        )
        await save_reply_and_latency(
            dependencies,
            request,
            session,
            intent_result,
            timing,
            loop_ms,
            total_ms,
            reply,
        )
        return reply
    reply = await postprocess_and_guard_reply(
        dependencies, request, session, timing, reply
    )
    await save_reply_and_latency(
        dependencies, request, session, intent_result, timing, loop_ms, total_ms, reply
    )
    context_budget = timing.get("context_budget")
    if dependencies.schedule_conversation_summary and isinstance(context_budget, dict):
        summary_request = ConversationSummaryAfterReplyRequest(session, context_budget)
        dependencies.schedule_conversation_summary(summary_request)
    return reply


async def save_reply_and_latency(
    dependencies: ChatMessageFlowDependencies,
    request: ChatMessageRequest,
    session: Session,
    intent_result: IntentDetectionResult,
    timing: dict,
    loop_ms: int,
    total_ms: int,
    reply: str | None,
) -> None:
    await save_assistant_reply(dependencies.message_repo, session.id, reply)
    await record_reply_latency(
        analytics_repo=dependencies.analytics_repo,
        session=session,
        user_id=request.user_id,
        channel=request.channel,
        intent=intent_result.intent,
        intent_ms=intent_result.intent_ms,
        timing=timing,
        loop_ms=loop_ms,
        total_ms=total_ms,
    )


def build_ai_failure_auto_transfer_context(
    dependencies: ChatMessageFlowDependencies,
    request: ChatMessageRequest,
    session: Session,
    history_text: str,
    failure_reason: str,
) -> AiFailureAutoTransferContext:
    return AiFailureAutoTransferContext(
        session=session,
        user_id=request.user_id,
        channel=request.channel,
        history_text=history_text,
        failure_reason=failure_reason,
        transfer_mgr=dependencies.transfer_mgr,
        session_repo=dependencies.session_repo,
        analytics_repo=dependencies.analytics_repo,
        fallback_reply=dependencies.fallback_reply,
        auto_transfer_reply=dependencies.auto_transfer_reply,
    )


async def run_ai_reply_loop(
    dependencies: ChatMessageFlowDependencies,
    request: ChatMessageRequest,
    session: Session,
    intent_result: IntentDetectionResult,
    timing: dict,
) -> str | None:
    customer_profile = await load_customer_profile(
        dependencies.customer_profile_repo,
        request.channel,
        request.user_id,
    )
    return await run_ai_conversation_loop(
        dependencies.ai_loop_dependencies,
        AiConversationLoopRequest(
            session=session,
            user_query=request.content,
            intent=intent_result.intent,
            timing=timing,
            history=intent_result.history,
            history_text=intent_result.history_text,
            image_base64=request.image_base64,
            customer_profile=customer_profile,
        ),
    )


async def postprocess_and_guard_reply(
    dependencies: ChatMessageFlowDependencies,
    request: ChatMessageRequest,
    session: Session,
    timing: dict,
    reply: str | None,
) -> str | None:
    reply = postprocess_reply(reply, user_content=request.content)
    return await apply_reply_guard(
        reply,
        ReplyGuardContext(
            analytics_repo=dependencies.analytics_repo,
            session=session,
            user_id=request.user_id,
            channel=request.channel,
            product_titles=tuple(timing.get("guard_product_titles") or ()),
            source_text=str(timing.get("guard_source_text") or ""),
        ),
    )


def get_ai_failure_reason(timing: dict) -> str:
    return str(timing.get(LLM_FAILURE_REASON_KEY) or "")
