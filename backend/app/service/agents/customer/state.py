"""客户机器人 LangGraph 状态模型。"""

from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from app.models.customer_profile import CustomerProfile
from app.models.session import Session
from app.service.agents.customer.memory import CustomerMemoryBlock
from app.service.agents.customer.tool_messages import ToolExecutionContext
from app.service.llm.intent import IntentType


class CustomerAgentState(TypedDict, total=False):
    """客户机器人单次 LangGraph 执行状态。"""

    session: Session
    user_query: str
    intent: IntentType
    timing: dict[str, Any] | None
    history: list[dict] | None
    history_text: str
    image_base64: str | None
    customer_profile: CustomerProfile | None
    memory_block: CustomerMemoryBlock
    messages: list[Any]
    tool_context: ToolExecutionContext
    tools_by_name: dict[str, Any]
    tool_node: Any
    has_image: bool
    fallback_reply: str
    timeout_reply: str
    failure_alerter: Callable[[str], Awaitable[None]]
    first_llm_started_at: float | None
    tool_round: int
    finish_reason: str
    llm_message: Any
    reply: str
    trace_events: list[dict[str, Any]]
