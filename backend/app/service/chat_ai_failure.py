"""AI 降级自动转人工边界。"""

import json
from dataclasses import dataclass
from typing import Any

from app.logger import setup_logger
from app.models.session import Session
from app.service.chat_transfer import HumanTransferContext, request_human_transfer
from app.utils import now_str

logger = setup_logger()

AI_FAILURE_AUTO_TRANSFER_EVENT_TYPE = "ai_failure_auto_transfer"
AI_FAILURE_AUTO_TRANSFER_EVENT_SOURCE = "chat_pipeline"
AI_FAILURE_AUTO_TRANSFER_DEFAULT_REASON = "AI 服务降级，自动转人工接手"


@dataclass(frozen=True)
class AiFailureAutoTransferContext:
    session: Session
    user_id: str
    channel: str
    history_text: str
    failure_reason: str
    transfer_mgr: Any
    session_repo: Any
    analytics_repo: Any
    fallback_reply: str
    auto_transfer_reply: str


async def handle_ai_failure_auto_transfer(
    context: AiFailureAutoTransferContext,
) -> str:
    transfer_created = await request_human_transfer(
        HumanTransferContext(
            session=context.session,
            user_id=context.user_id,
            reason=f"{AI_FAILURE_AUTO_TRANSFER_DEFAULT_REASON}: {context.failure_reason}",
            history_text=context.history_text,
            transfer_mgr=context.transfer_mgr,
            session_repo=context.session_repo,
        )
    )
    await record_ai_failure_auto_transfer(context, transfer_created)
    if transfer_created:
        return context.auto_transfer_reply
    return context.fallback_reply


async def record_ai_failure_auto_transfer(
    context: AiFailureAutoTransferContext,
    transfer_created: bool,
) -> None:
    try:
        await context.analytics_repo.add_event(
            session_id=context.session.id,
            buyer_id=context.user_id,
            event_type=AI_FAILURE_AUTO_TRANSFER_EVENT_TYPE,
            event_source=AI_FAILURE_AUTO_TRANSFER_EVENT_SOURCE,
            ref_id=context.session.id,
            meta_data=json.dumps(
                {
                    "channel": context.channel,
                    "failure_reason": context.failure_reason,
                    "transfer_created": transfer_created,
                },
                ensure_ascii=False,
            ),
            created_at=now_str(),
        )
    except Exception as exc:
        logger.warning("AI 降级转人工埋点失败: %s", exc)
