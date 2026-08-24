"""客户机器人 LangGraph 节点。"""

from typing import Any

from app.service.agents.customer.contracts import CustomerGraphDependencies
from app.service.agents.customer.state import CustomerAgentState
from app.service.agents.customer.constants import CUSTOMER_TOOL_ROUND_LIMIT
from app.service.agents.customer.memory import load_customer_memory_block
from app.service.agents.tools.customer import CustomerToolContext
from app.service.agents.tools.registry import build_tools
from app.service.agents.customer.support import (
    build_transfer_handler,
    extend_guard_source_with_tool_outputs,
    record_tool_round_limit,
    record_tool_rounds,
)
from app.service.chat_context import prepare_ai_conversation_messages
from app.service.chat_context_budget import record_tool_context_budget_delta
from app.service.agents.messages import to_langchain_messages
from app.service.agents.customer.model import (
    CustomerModelRequest,
    request_customer_model_with_tools,
)
from app.service.agents.observability import (
    append_trace_event,
    build_node_trace_event,
)
from app.service.agents.tool_node import load_tool_node_class
from app.service.agents.customer.tool_messages import (
    ToolExecutionContext,
)
from app.service.llm.constants import LLM_FAILURE_REASON_KEY
from app.service.llm.intent import IntentType


class CustomerAgentNodes:
    """客户机器人 LangGraph 节点集合。"""

    def __init__(self, dependencies: CustomerGraphDependencies) -> None:
        self._dependencies = dependencies

    async def load_session_context(
        self,
        state: CustomerAgentState,
    ) -> CustomerAgentState:
        """加载会话上下文、RAG 上下文和工具上下文。"""
        memory_block = await load_customer_memory_block(
            summary_repo=self._dependencies.conversation_summary_repo,
            session_id=state["session"].id,
            customer_profile=state.get("customer_profile"),
        )
        messages, history_text = await prepare_ai_conversation_messages(
            session_mgr=self._dependencies.session_mgr,
            knowledge=self._dependencies.knowledge,
            session=state["session"],
            user_query=state.get("user_query", ""),
            intent=state.get("intent", IntentType.PRODUCT_CONSULTATION),
            timing=state.get("timing"),
            history=state.get("history"),
            history_text=state.get("history_text", ""),
            image_base64=state.get("image_base64"),
            customer_profile=memory_block.customer_profile,
            conversation_summary_text=memory_block.conversation_summary_text,
        )
        tool_context = ToolExecutionContext(
            session=state["session"],
            history_text=history_text,
            transfer_mgr=self._dependencies.transfer_mgr,
            session_repo=self._dependencies.session_repo,
            knowledge=self._dependencies.knowledge,
            youzan_client=self._dependencies.youzan_client,
            order_repo=self._dependencies.order_repo,
            config_repo=self._dependencies.config_repo,
            product_repo=self._dependencies.product_repo,
            knowledge_product_repo=self._dependencies.knowledge_product_repo,
            analytics_repo=self._dependencies.analytics_repo,
            history_repo=self._dependencies.history_repo,
            embedding_searcher=getattr(
                self._dependencies.knowledge,
                "embedding_searcher",
                None,
            ),
        )
        return {
            **state,
            "messages": to_langchain_messages(messages),
            "history_text": history_text,
            "memory_block": memory_block,
            "tool_context": tool_context,
            "has_image": bool(state.get("image_base64")),
            "fallback_reply": self._dependencies.fallback_reply,
            "timeout_reply": self._dependencies.timeout_reply,
            "failure_alerter": self._dependencies.failure_alerter,
            "first_llm_started_at": None,
            "tool_round": 0,
            "trace_events": [
                _build_memory_trace_event(memory_block, state.get("timing"))
            ],
        }

    async def model_with_tools(
        self,
        state: CustomerAgentState,
    ) -> CustomerAgentState:
        """请求模型并记录本轮 finish_reason。"""
        tools_by_name = self._tools_by_name(state)
        llm_result = await request_customer_model_with_tools(
            CustomerModelRequest(
                messages=state["messages"],
                tools=list(tools_by_name.values()),
                timing=state.get("timing"),
                first_llm_started_at=state.get("first_llm_started_at"),
                has_image=state["has_image"],
                fallback_reply=state["fallback_reply"],
                failure_alerter=state["failure_alerter"],
            )
        )
        if llm_result.fallback_reply is not None:
            return {
                **state,
                "reply": llm_result.fallback_reply,
                "first_llm_started_at": llm_result.first_llm_started_at,
                "trace_events": append_trace_event(
                    state.get("trace_events"),
                    "model_with_tools",
                    finish_reason="fallback",
                    model=getattr(llm_result, "model_name", ""),
                    latency_ms=_timing_value(state, "llm_ms"),
                    fallback_reason=_timing_value(state, LLM_FAILURE_REASON_KEY),
                ),
            }
        message = llm_result.message
        assert message is not None
        return {
            **state,
            "finish_reason": llm_result.finish_reason,
            "llm_message": message,
            "tools_by_name": tools_by_name,
            "first_llm_started_at": llm_result.first_llm_started_at,
            "trace_events": append_trace_event(
                state.get("trace_events"),
                "model_with_tools",
                finish_reason=llm_result.finish_reason,
                model=getattr(llm_result, "model_name", ""),
                latency_ms=_timing_value(state, "llm_ms"),
                tool_call_count=len(message.tool_calls or []),
            ),
        }

    async def execute_tools(self, state: CustomerAgentState) -> CustomerAgentState:
        """通过 LangGraph ToolNode 执行 customer tools。"""
        message_count_before_tools = len(state["messages"])
        tool_node = state.get("tool_node") or self._build_tool_node(state)
        tool_result = await tool_node.ainvoke({"messages": [state["llm_message"]]})
        tool_messages = tool_result.get("messages") or []
        state["messages"].extend([state["llm_message"], *tool_messages])
        tool_names = [
            str(tool_call.get("name", ""))
            for tool_call in state["llm_message"].tool_calls or []
        ]
        record_tool_context_budget_delta(
            state.get("timing"),
            state["messages"][message_count_before_tools:],
        )
        tool_round = state.get("tool_round", 0) + 1
        return {
            **state,
            "tool_round": tool_round,
            "tool_node": tool_node,
            "trace_events": append_trace_event(
                state.get("trace_events"),
                "execute_tools",
                tool_round=tool_round,
                tool_name=tool_names[0] if len(tool_names) == 1 else "",
                tool_names=tool_names,
                tool_call_count=len(tool_names),
            ),
        }

    async def finalize_reply(self, state: CustomerAgentState) -> CustomerAgentState:
        """生成最终回复并记录工具轮次。"""
        reply = state.get("reply", "")
        if not reply:
            message = state.get("llm_message")
            reply = str(message.content or "") if message is not None else ""
        record_tool_rounds(state.get("timing"), state.get("tool_round", 0))
        return {
            **state,
            "reply": reply,
            "trace_events": append_trace_event(
                state.get("trace_events"),
                "finalize_reply",
            ),
        }

    async def tool_round_limit(
        self,
        state: CustomerAgentState,
    ) -> CustomerAgentState:
        """工具轮次超限时返回超时兜底。"""
        record_tool_rounds(state.get("timing"), state.get("tool_round", 0))
        record_tool_round_limit(state.get("timing"))
        return {
            **state,
            "reply": state["timeout_reply"],
            "trace_events": append_trace_event(
                state.get("trace_events"),
                "tool_round_limit",
            ),
        }

    async def record_trace(self, state: CustomerAgentState) -> CustomerAgentState:
        """结束前补充 guard source。"""
        extend_guard_source_with_tool_outputs(
            state.get("timing"),
            state.get("messages", []),
        )
        return {
            **state,
            "trace_events": append_trace_event(
                state.get("trace_events"),
                "record_trace",
            ),
        }

    def _tools_by_name(self, state: CustomerAgentState) -> dict[str, Any]:
        tools_by_name = state.get("tools_by_name")
        if tools_by_name is not None:
            return tools_by_name
        return self._build_tools(state["tool_context"])

    def _build_tools(self, tool_context: ToolExecutionContext) -> dict[str, Any]:
        context = CustomerToolContext(
            session=tool_context.session,
            knowledge_retriever=tool_context.knowledge,
            youzan_client=tool_context.youzan_client,
            order_repo=tool_context.order_repo,
            config_repo=tool_context.config_repo,
            product_repo=tool_context.product_repo,
            knowledge_product_repo=tool_context.knowledge_product_repo,
            analytics_repo=tool_context.analytics_repo,
            history_repo=tool_context.history_repo,
            embedding_searcher=tool_context.embedding_searcher,
            transfer_handler=build_transfer_handler(tool_context),
        )
        return {
            tool.name: tool
            for tool in build_tools("customer", customer_context=context)
        }

    def _build_tool_node(self, state: CustomerAgentState) -> Any:
        ToolNode = load_tool_node_class()
        return ToolNode(
            list(self._tools_by_name(state).values()), handle_tool_errors=True
        )


def route_after_model(state: CustomerAgentState) -> str:
    """根据模型返回决定继续工具轮次或结束。"""
    if state.get("reply"):
        return "finalize"
    if state.get("finish_reason") == "stop":
        return "finalize"
    if (
        state.get("finish_reason") == "tool_calls"
        and state.get("tool_round", 0) < CUSTOMER_TOOL_ROUND_LIMIT
    ):
        return "tools"
    return "limit"


def _build_memory_trace_event(
    memory_block: Any,
    timing: dict[str, Any] | None,
) -> dict[str, Any]:
    context_budget = (timing or {}).get("context_budget") or {}
    return build_node_trace_event(
        "load_session_context",
        memory={
            "conversation_summary": memory_block.has_conversation_summary,
            "customer_profile": memory_block.has_customer_profile,
        },
        latency_ms=(timing or {}).get("rag_ms"),
        knowledge_entry_ids=(timing or {}).get("knowledge_entry_ids") or [],
        knowledge_hit_count=context_budget.get("knowledge_entry_count", 0),
    )


def _timing_value(state: CustomerAgentState, key: str) -> Any:
    timing = state.get("timing") or {}
    return timing.get(key)
