"""员工助手 LangGraph 节点。"""

from dataclasses import dataclass
from typing import Any, cast
import json

from app.models.employee_agent import AgentIntent, AgentPlan, ToolResult
from app.service.agents.employee.state import EmployeeAgentState
from app.service.agents.observability import (
    append_trace_event,
    build_node_trace_event,
)
from app.service.agents.tool_node import load_tool_node_class
from app.service.agents.tools.employee import (
    DEFAULT_EMPLOYEE_TOOL_LIMIT,
    EmployeeToolContext,
)
from app.service.agents.tools.registry import build_tools
from app.service.wecom.employee_agent_mixed_reply import build_mixed_tool_reply
from app.service.wecom.employee_agent_ops_plan import extract_campaign_id
from app.service.wecom.employee_agent_planner import EmployeeAgentPlanner

UNSUPPORTED_REPLY = (
    "我还没理解这个问题。你可以直接问订单、商品库存、配送规则、待人工或系统状态。"
)
HUMAN_HANDOFF_REPLY = "当前信息无法可靠确认，我先为您转人工核对，请稍候。"
UNAUTHORIZED_TOOL_REPLY = "当前员工身份无权调用该工具，请联系管理员授权。"
FACT_UNAVAILABLE_MARKERS = (
    "未找到匹配商品",
    "未找到匹配订单",
    "未找到匹配知识",
    "未找到客户",
    "未找到该客户",
    "暂不可用",
    "无法确认",
    "需要人工继续核对",
)
HANDOFF_QUERY_MARKERS = ("需要注意", "有什么要盯", "要盯")
EMPLOYEE_TOOL_CALL_ID_PREFIX = "employee"


@dataclass(frozen=True)
class EmployeeGraphDependencies:
    """员工助手 graph 运行依赖。"""

    business_tool_service: Any
    ops_tool_service: Any
    status_tool_service: Any
    order_lookup_service: Any = None
    planner: EmployeeAgentPlanner | None = None
    trace_sink: Any | None = None


class EmployeeAgentNodes:
    """员工助手 LangGraph 节点集合。"""

    def __init__(self, dependencies: EmployeeGraphDependencies) -> None:
        self._dependencies = dependencies
        self._planner = dependencies.planner or EmployeeAgentPlanner()
        self._tools_by_name: dict[str, Any] | None = None
        self._tool_node: Any | None = None

    async def load_employee_context(
        self,
        state: EmployeeAgentState,
    ) -> EmployeeAgentState:
        """初始化员工助手执行上下文。"""
        query = state.get("query", "")
        return {
            **state,
            "query": query,
            "trace_events": [build_node_trace_event("load_employee_context")],
        }

    async def plan_intent(self, state: EmployeeAgentState) -> EmployeeAgentState:
        """生成员工助手结构化执行计划。"""
        plan = await self._planner.plan(state["query"])
        return {
            **state,
            "plan": plan,
            "trace_events": append_trace_event(
                state.get("trace_events"),
                "plan_intent",
                intent=plan.intent.value,
                tools=list(plan.tools),
            ),
        }

    async def select_tools(self, state: EmployeeAgentState) -> EmployeeAgentState:
        """把计划转换成要执行的工具名称。"""
        plan = state["plan"]
        selected_tools = _selected_tools(plan)
        return {
            **state,
            "selected_tools": selected_tools,
            "trace_events": append_trace_event(
                state.get("trace_events"),
                "select_tools",
                tools=list(selected_tools),
                tool_name=selected_tools[0] if len(selected_tools) == 1 else "",
                tool_call_count=len(selected_tools),
            ),
        }

    async def execute_tools(self, state: EmployeeAgentState) -> EmployeeAgentState:
        """执行 LangChain 工具并保留计划化订单查询路径。"""
        plan = state["plan"]
        query = state["query"]
        results: list[ToolResult] = []
        for tool_name in state.get("selected_tools", ()):
            if not _is_tool_allowed(state, tool_name):
                results.append(ToolResult(ok=False, summary=UNAUTHORIZED_TOOL_REPLY))
                continue
            results.append(await self._execute_tool(tool_name, query, plan))
        if not results:
            results.append(ToolResult(ok=False, summary=UNSUPPORTED_REPLY))
        return {
            **state,
            "tool_results": results,
            "trace_events": append_trace_event(
                state.get("trace_events"),
                "execute_tools",
                count=len(results),
                tool_name=state["selected_tools"][0]
                if len(state.get("selected_tools", ())) == 1
                else "",
                tool_call_count=len(state.get("selected_tools", ())),
            ),
        }

    async def validate_tool_facts(
        self,
        state: EmployeeAgentState,
    ) -> EmployeeAgentState:
        """记录工具事实校验结果。"""
        ok_count = sum(1 for result in state.get("tool_results", []) if result.ok)
        return {
            **state,
            "trace_events": append_trace_event(
                state.get("trace_events"),
                "validate_tool_facts",
                ok_count=ok_count,
            ),
        }

    async def deterministic_finalizer(
        self,
        state: EmployeeAgentState,
    ) -> EmployeeAgentState:
        """用确定性模板生成最终回复，不做 LLM 润色。"""
        reply = deterministic_reply(
            state["query"],
            state["plan"],
            state.get("tool_results", []),
        )
        return {
            **state,
            "reply": reply,
            "trace_events": append_trace_event(
                state.get("trace_events"),
                "deterministic_finalizer",
                final_status="success",
            ),
        }

    async def record_trace(self, state: EmployeeAgentState) -> EmployeeAgentState:
        """结束前记录本地 trace 事件。"""
        return {
            **state,
            "trace_events": append_trace_event(
                state.get("trace_events"),
                "record_trace",
            ),
        }

    async def _execute_tool(
        self,
        tool_name: str,
        query: str,
        plan: AgentPlan,
    ) -> ToolResult:
        if tool_name == "order_dynamic_query":
            return await self._run_order_tool(query, plan)
        tool = self._tools().get(tool_name)
        if tool is None:
            return ToolResult(ok=False, summary=UNSUPPORTED_REPLY)
        return await self._execute_with_tool_node(
            tool_name,
            _tool_args(tool_name, query, plan),
        )

    async def _run_order_tool(self, query: str, plan: AgentPlan) -> ToolResult:
        service = self._dependencies.order_lookup_service
        if service is not None and plan.query_plan is not None:
            return cast(
                ToolResult,
                await service.answer_agent_query(query, plan.query_plan),
            )
        tool = self._tools().get("order_dynamic_query")
        if tool is None:
            return ToolResult(ok=False, summary=UNSUPPORTED_REPLY)
        return await self._execute_with_tool_node(
            "order_dynamic_query",
            {"query": query, "limit": DEFAULT_EMPLOYEE_TOOL_LIMIT},
        )

    async def _execute_with_tool_node(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """通过 LangGraph 标准节点执行一个已选工具。"""
        from langchain_core.messages import AIMessage

        result = await self._tool_node_instance().ainvoke(
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": tool_name,
                                "args": arguments,
                                "id": f"{EMPLOYEE_TOOL_CALL_ID_PREFIX}-{tool_name}",
                                "type": "tool_call",
                            }
                        ],
                    )
                ]
            }
        )
        messages = result.get("messages", [])
        if not messages:
            return ToolResult(ok=False, summary=UNSUPPORTED_REPLY)
        return tool_result_from_payload(_json_payload(messages[-1].content))

    def _tool_node_instance(self) -> Any:
        if self._tool_node is None:
            ToolNode = load_tool_node_class()
            self._tool_node = ToolNode(list(self._tools().values()))
        return self._tool_node

    def _tools(self) -> dict[str, Any]:
        if self._tools_by_name is None:
            context = EmployeeToolContext(
                business_tool_service=self._dependencies.business_tool_service,
                ops_tool_service=self._dependencies.ops_tool_service,
                status_tool_service=self._dependencies.status_tool_service,
            )
            self._tools_by_name = {
                tool.name: tool
                for tool in build_tools("employee", employee_context=context)
            }
        return self._tools_by_name


def deterministic_reply(
    query: str,
    plan: AgentPlan,
    tool_results: list[ToolResult],
) -> str:
    """生成员工助手确定性回复。"""
    if any(marker in query for marker in HANDOFF_QUERY_MARKERS):
        return HUMAN_HANDOFF_REPLY
    if any(not result.ok for result in tool_results):
        return HUMAN_HANDOFF_REPLY
    if any(
        marker in result.summary
        for result in tool_results
        for marker in FACT_UNAVAILABLE_MARKERS
    ):
        return HUMAN_HANDOFF_REPLY
    mixed_reply = build_mixed_tool_reply(query, plan, tool_results)
    if mixed_reply is not None:
        return cast(str, mixed_reply)
    lines = [result.summary for result in tool_results if result.summary.strip()]
    if not lines:
        return UNSUPPORTED_REPLY
    next_actions = [
        result.next_action for result in tool_results if result.next_action.strip()
    ]
    if next_actions:
        lines.append("下一步：" + "；".join(next_actions))
    return "\n".join(lines)


def tool_result_from_payload(payload: dict[str, Any]) -> ToolResult:
    """把 LangChain 工具 JSON 结果转成员工助手 ToolResult。"""
    return ToolResult(
        ok=bool(payload.get("ok", False)),
        summary=str(
            payload.get("result")
            or payload.get("resultText")
            or payload.get("summary")
            or ""
        ),
        items=_extract_items(payload),
        metrics=_extract_metrics(payload),
        next_action=str(payload.get("nextAction", "")),
    )


def _selected_tools(plan: AgentPlan) -> tuple[str, ...]:
    if plan.intent == AgentIntent.ORDER_QUERY:
        return ("order_dynamic_query",)
    if plan.intent == AgentIntent.PRODUCT_QUERY:
        return ("product_lookup",)
    if plan.intent == AgentIntent.KNOWLEDGE_ANSWER:
        return ("knowledge_answer",)
    if plan.intent in (AgentIntent.OPS_QUERY, AgentIntent.MULTI_TOOL):
        return cast(tuple[str, ...], plan.tools)
    return ()


def _is_tool_allowed(state: EmployeeAgentState, tool_name: str) -> bool:
    allowed_tools = state.get("allowed_tools")
    return allowed_tools is None or tool_name in allowed_tools


def _tool_args(tool_name: str, query: str, plan: AgentPlan) -> dict[str, Any]:
    if tool_name == "product_lookup":
        product_query = query
        if plan.query_plan is not None and plan.query_plan.keyword:
            product_query = plan.query_plan.keyword
        return {"query": product_query, "limit": DEFAULT_EMPLOYEE_TOOL_LIMIT}
    if tool_name == "knowledge_answer":
        return {"question": query, "limit": DEFAULT_EMPLOYEE_TOOL_LIMIT}
    if tool_name == "group_campaign_summary":
        return {
            "campaign_id": extract_campaign_id(query),
            "limit": DEFAULT_EMPLOYEE_TOOL_LIMIT,
        }
    if tool_name in {"ops_summary", "handoff_pending", "offline_review_summary"}:
        return {"limit": DEFAULT_EMPLOYEE_TOOL_LIMIT}
    return {"query": query, "limit": DEFAULT_EMPLOYEE_TOOL_LIMIT}


def _json_payload(raw_result: Any) -> dict[str, Any]:
    if isinstance(raw_result, dict):
        return raw_result
    if not isinstance(raw_result, str):
        return {"ok": False, "result": str(raw_result)}
    try:
        payload = json.loads(raw_result)
    except json.JSONDecodeError:
        return {"ok": False, "result": raw_result}
    return payload if isinstance(payload, dict) else {"ok": False, "result": raw_result}


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("orders", "products", "sources", "addresses", "transfers", "webhooks"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _extract_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("counts") or payload.get("metrics")
    return value if isinstance(value, dict) else {}
