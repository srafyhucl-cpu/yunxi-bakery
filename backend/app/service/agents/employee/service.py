"""员工助手 LangGraph application adapter。"""

from app.service.agents.employee.graph import build_employee_agent_graph
from app.service.agents.employee.nodes import EmployeeGraphDependencies
from app.service.agents.employee.state import EmployeeAgentState
from app.service.agents.trace_report import AgentTraceRun
from app.service.agents.trace_sink import AgentTraceSink
from app.logger import setup_logger

logger = setup_logger()


class EmployeeAgentGraphService:
    """员工助手 LangGraph 编排服务。"""

    def __init__(self, dependencies: EmployeeGraphDependencies) -> None:
        self._dependencies = dependencies
        self._graph = None

    async def answer(
        self,
        query: str,
        *,
        allowed_tools: frozenset[str] | None = None,
    ) -> str:
        """执行员工助手 LangGraph 并返回原始确定性回复。"""
        reply, _trace_run = await self.answer_with_trace(
            query,
            allowed_tools=allowed_tools,
        )
        return reply

    async def answer_with_trace(
        self,
        query: str,
        *,
        allowed_tools: frozenset[str] | None = None,
    ) -> tuple[str, AgentTraceRun]:
        """执行员工助手 LangGraph 并返回脱敏 trace。"""
        state: EmployeeAgentState = {"query": query}
        if allowed_tools is not None:
            state["allowed_tools"] = tuple(sorted(allowed_tools))
        result = await self._compiled_graph().ainvoke(state)
        reply = str(result.get("reply", ""))
        trace_run = AgentTraceRun(
            agent="employee",
            trace_events=tuple(result.get("trace_events") or ()),
            channel="wecom_employee",
            final_status=_final_status(result),
        )
        await _write_trace(self._dependencies.trace_sink, trace_run)
        return reply, trace_run

    def _compiled_graph(self):
        if self._graph is None:
            self._graph = build_employee_agent_graph(self._dependencies)
        return self._graph


def _final_status(result: dict) -> str:
    trace_events = result.get("trace_events") or ()
    if any(event.get("fallback_reason") for event in trace_events):
        return "fallback"
    if any(event.get("finish_reason") == "fallback" for event in trace_events):
        return "fallback"
    return "success"


async def _write_trace(
    trace_sink: AgentTraceSink | None,
    trace_run: AgentTraceRun,
) -> None:
    if trace_sink is None:
        return
    try:
        await trace_sink.write(trace_run)
    except Exception as exc:
        logger.error("员工 Agent trace sink 写入失败: %s", exc)
