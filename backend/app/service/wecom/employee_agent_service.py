"""企微员工助手 Agent 编排服务。"""

from __future__ import annotations

from typing import Any, cast

from app.service.chat_reply import clean_plain_text_reply
from app.service.agents.employee.nodes import EmployeeGraphDependencies
from app.service.agents.employee.service import EmployeeAgentGraphService
from app.service.agents.trace_sink import AgentTraceSink
from app.service.wecom.employee_agent_planner import EmployeeAgentPlanner


class EmployeeAgentService:
    """面向企微员工群的全业务 Agent 总编排。"""

    def __init__(
        self,
        *,
        business_tool_service: Any,
        ops_tool_service: Any,
        status_tool_service: Any,
        order_lookup_service: Any = None,
        planner: EmployeeAgentPlanner | None = None,
        trace_sink: AgentTraceSink | None = None,
    ) -> None:
        self._business_tool_service = business_tool_service
        self._ops_tool_service = ops_tool_service
        self._status_tool_service = status_tool_service
        self._order_lookup_service = order_lookup_service
        self._planner = planner or EmployeeAgentPlanner()
        self._graph_service = EmployeeAgentGraphService(
            EmployeeGraphDependencies(
                business_tool_service=business_tool_service,
                ops_tool_service=ops_tool_service,
                status_tool_service=status_tool_service,
                order_lookup_service=order_lookup_service,
                planner=self._planner,
                trace_sink=trace_sink,
            )
        )

    async def answer(
        self,
        query: str,
        *,
        allowed_tools: frozenset[str] | None = None,
    ) -> str:
        """回答员工自然语言问题。"""
        deterministic_reply = await self._graph_service.answer(
            query,
            allowed_tools=allowed_tools,
        )
        return cast(str, clean_plain_text_reply(deterministic_reply))
