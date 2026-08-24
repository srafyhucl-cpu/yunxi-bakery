"""Agent 运行时通用模型。"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentRuntimeContext:
    """一次 Agent 调用的运行上下文。"""

    trace_id: str = ""
    bot_type: str = ""
    channel: str = ""
    user_id: str = ""
    session_id: str = ""


@dataclass(frozen=True)
class AgentResult:
    """Agent 编排结果。"""

    reply: str
    fallback_reason: str = ""
    handoff_required: bool = False
    metadata: dict[str, str] = field(default_factory=dict)
