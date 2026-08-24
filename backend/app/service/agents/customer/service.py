"""客户机器人 LangGraph application adapter。"""

from app.service.agents.customer.graph import build_customer_agent_graph
from app.service.agents.customer.contracts import (
    CustomerGraphDependencies,
    CustomerGraphRequest,
    initial_customer_state,
)
from app.service.agents.trace_report import AgentTraceRun
from app.service.agents.trace_sink import AgentTraceSink
from app.logger import setup_logger

logger = setup_logger()

CUSTOMER_THREAD_NAMESPACE = "customer"


class CustomerAgentGraphService:
    """客户机器人 LangGraph 编排服务。"""

    def __init__(self, dependencies: CustomerGraphDependencies) -> None:
        self._dependencies = dependencies
        self._graph = None

    async def answer(self, request: CustomerGraphRequest) -> str:
        """执行客户机器人 LangGraph 并返回回复。"""
        reply, _trace_run = await self.answer_with_trace(request)
        return reply

    async def answer_with_trace(
        self,
        request: CustomerGraphRequest,
    ) -> tuple[str, AgentTraceRun]:
        """执行客户机器人 LangGraph 并返回脱敏 trace。"""
        result = await self._compiled_graph().ainvoke(
            initial_customer_state(request),
            config={
                "configurable": {
                    "thread_id": f"{CUSTOMER_THREAD_NAMESPACE}:{request.session.id}"
                }
            },
        )
        reply = str(result.get("reply", ""))
        trace_run = AgentTraceRun(
            agent="customer",
            trace_events=tuple(result.get("trace_events") or ()),
            conversation_id=request.session.id,
            channel=request.session.channel,
            final_status=_final_status(result),
        )
        await _write_trace(self._dependencies.trace_sink, trace_run)
        return reply, trace_run

    def _compiled_graph(self):
        if self._graph is None:
            self._graph = build_customer_agent_graph(self._dependencies)
        return self._graph


def _final_status(result: dict) -> str:
    trace_events = result.get("trace_events") or ()
    if any(event.get("fallback_reason") for event in trace_events):
        return "fallback"
    if any(event.get("finish_reason") == "fallback" for event in trace_events):
        return "fallback"
    if any(event.get("node") == "tool_round_limit" for event in trace_events):
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
        logger.error("客户 Agent trace sink 写入失败: %s", exc)
