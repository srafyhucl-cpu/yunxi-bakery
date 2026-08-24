"""客户机器人 LangGraph 构建入口。"""

from typing import Any

from app.service.agents.customer.nodes import (
    CustomerAgentNodes,
    route_after_model,
)
from app.service.agents.customer.contracts import CustomerGraphDependencies
from app.service.agents.customer.state import CustomerAgentState


def build_customer_agent_graph(dependencies: CustomerGraphDependencies) -> Any:
    """懒加载并构造客户机器人 LangGraph。"""
    from langgraph.graph import END, START, StateGraph

    nodes = CustomerAgentNodes(dependencies)
    graph = StateGraph(CustomerAgentState)
    graph.add_node("load_session_context", nodes.load_session_context)
    graph.add_node("model_with_tools", nodes.model_with_tools)
    graph.add_node("execute_tools", nodes.execute_tools)
    graph.add_node("finalize_reply", nodes.finalize_reply)
    graph.add_node("tool_round_limit", nodes.tool_round_limit)
    graph.add_node("record_trace", nodes.record_trace)

    graph.add_edge(START, "load_session_context")
    graph.add_edge("load_session_context", "model_with_tools")
    graph.add_conditional_edges(
        "model_with_tools",
        route_after_model,
        {
            "tools": "execute_tools",
            "finalize": "finalize_reply",
            "limit": "tool_round_limit",
        },
    )
    graph.add_edge("execute_tools", "model_with_tools")
    graph.add_edge("finalize_reply", "record_trace")
    graph.add_edge("tool_round_limit", "record_trace")
    graph.add_edge("record_trace", END)
    return graph.compile()
