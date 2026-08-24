"""AI 对话循环编排边界。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.models.session import Session
from app.models.customer_profile import CustomerProfile
from app.repository.session_repo import SessionRepo
from app.service.agents.customer.contracts import (
    CustomerGraphDependencies,
    CustomerGraphRequest,
)
from app.service.agents.customer.service import CustomerAgentGraphService
from app.service.agents.trace_sink import AgentTraceSink
from app.service.conversation_summary_memory import (
    ConversationSummaryReader,
)
from app.service.knowledge_retriever import KnowledgeRetriever
from app.service.llm.intent import IntentType
from app.service.session_manager import SessionManager
from app.service.transfer_manager import TransferManager
from app.service.youzan.client import YouzanClient


@dataclass(frozen=True)
class AiConversationLoopDependencies:
    session_mgr: SessionManager
    knowledge: KnowledgeRetriever
    transfer_mgr: TransferManager
    session_repo: SessionRepo
    youzan_client: YouzanClient
    fallback_reply: str
    timeout_reply: str
    failure_alerter: Callable[[str], Awaitable[None]]
    order_repo: object | None = None
    config_repo: object | None = None
    product_repo: object | None = None
    knowledge_product_repo: object | None = None
    analytics_repo: object | None = None
    history_repo: object | None = None
    conversation_summary_repo: ConversationSummaryReader | None = None
    trace_sink: AgentTraceSink | None = None


@dataclass(frozen=True)
class AiConversationLoopRequest:
    session: Session
    user_query: str = ""
    intent: IntentType = IntentType.PRODUCT_CONSULTATION
    timing: dict | None = None
    history: list[dict] | None = None
    history_text: str = ""
    image_base64: str | None = None
    customer_profile: CustomerProfile | None = None


async def run_ai_conversation_loop(
    dependencies: AiConversationLoopDependencies,
    request: AiConversationLoopRequest,
) -> str | None:
    graph_service = CustomerAgentGraphService(
        CustomerGraphDependencies(
            session_mgr=dependencies.session_mgr,
            knowledge=dependencies.knowledge,
            transfer_mgr=dependencies.transfer_mgr,
            session_repo=dependencies.session_repo,
            youzan_client=dependencies.youzan_client,
            order_repo=dependencies.order_repo,
            config_repo=dependencies.config_repo,
            product_repo=dependencies.product_repo,
            knowledge_product_repo=dependencies.knowledge_product_repo,
            analytics_repo=dependencies.analytics_repo,
            history_repo=dependencies.history_repo,
            fallback_reply=dependencies.fallback_reply,
            timeout_reply=dependencies.timeout_reply,
            failure_alerter=dependencies.failure_alerter,
            conversation_summary_repo=dependencies.conversation_summary_repo,
            trace_sink=dependencies.trace_sink,
        )
    )
    return await graph_service.answer(
        CustomerGraphRequest(
            session=request.session,
            user_query=request.user_query,
            intent=request.intent,
            timing=request.timing,
            history=request.history,
            history_text=request.history_text,
            image_base64=request.image_base64,
            customer_profile=request.customer_profile,
        )
    )
