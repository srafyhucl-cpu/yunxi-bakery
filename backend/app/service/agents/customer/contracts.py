"""客户机器人 graph 契约模型。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.models.customer_profile import CustomerProfile
from app.models.session import Session
from app.service.agents.customer.state import CustomerAgentState
from app.service.conversation_summary_memory import ConversationSummaryReader
from app.service.knowledge_retriever import KnowledgeRetriever
from app.service.llm.intent import IntentType
from app.service.session_manager import SessionManager
from app.service.transfer_manager import TransferManager
from app.service.youzan.client import YouzanClient


@dataclass(frozen=True)
class CustomerGraphDependencies:
    """客户机器人 graph 运行依赖。"""

    session_mgr: SessionManager
    knowledge: KnowledgeRetriever
    transfer_mgr: TransferManager
    session_repo: Any
    youzan_client: YouzanClient
    fallback_reply: str
    timeout_reply: str
    failure_alerter: Callable[[str], Awaitable[None]]
    order_repo: Any = None
    config_repo: Any = None
    product_repo: Any = None
    knowledge_product_repo: Any = None
    analytics_repo: Any = None
    history_repo: Any = None
    conversation_summary_repo: ConversationSummaryReader | None = None
    trace_sink: Any | None = None


@dataclass(frozen=True)
class CustomerGraphRequest:
    """客户机器人 graph 单次请求。"""

    session: Session
    user_query: str = ""
    intent: IntentType = IntentType.PRODUCT_CONSULTATION
    timing: dict[str, Any] | None = None
    history: list[dict] | None = None
    history_text: str = ""
    image_base64: str | None = None
    customer_profile: CustomerProfile | None = None


def initial_customer_state(request: CustomerGraphRequest) -> CustomerAgentState:
    """把请求转换为 LangGraph 初始状态。"""
    return {
        "session": request.session,
        "user_query": request.user_query,
        "intent": request.intent,
        "timing": request.timing,
        "history": request.history,
        "history_text": request.history_text,
        "image_base64": request.image_base64,
        "customer_profile": request.customer_profile,
    }
