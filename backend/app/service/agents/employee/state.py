"""员工助手 LangGraph 状态模型。"""

from typing import Any, TypedDict

from app.models.employee_agent import AgentPlan, ToolResult


class EmployeeAgentState(TypedDict, total=False):
    """员工助手单次 LangGraph 执行状态。"""

    query: str
    plan: AgentPlan
    selected_tools: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    tool_results: list[ToolResult]
    reply: str
    trace_events: list[dict[str, Any]]
    error: str
