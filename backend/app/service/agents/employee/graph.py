"""员工助手 LangGraph 构建入口。"""

from typing import Any

from app.service.agents.employee.nodes import (
    EmployeeAgentNodes,
    EmployeeGraphDependencies,
)
from app.service.agents.employee.state import EmployeeAgentState


def build_employee_agent_graph(dependencies: EmployeeGraphDependencies) -> Any:
    """懒加载并构造员工助手 LangGraph。"""
    from langgraph.graph import END, START, StateGraph

    nodes = EmployeeAgentNodes(dependencies)
    graph = StateGraph(EmployeeAgentState)
    graph.add_node("load_employee_context", nodes.load_employee_context)
    graph.add_node("plan_intent", nodes.plan_intent)
    graph.add_node("select_tools", nodes.select_tools)
    graph.add_node("execute_tools", nodes.execute_tools)
    graph.add_node("validate_tool_facts", nodes.validate_tool_facts)
    graph.add_node("deterministic_finalizer", nodes.deterministic_finalizer)
    graph.add_node("record_trace", nodes.record_trace)

    graph.add_edge(START, "load_employee_context")
    graph.add_edge("load_employee_context", "plan_intent")
    graph.add_edge("plan_intent", "select_tools")
    graph.add_edge("select_tools", "execute_tools")
    graph.add_edge("execute_tools", "validate_tool_facts")
    graph.add_edge("validate_tool_facts", "deterministic_finalizer")
    graph.add_edge("deterministic_finalizer", "record_trace")
    graph.add_edge("record_trace", END)
    return graph.compile()
