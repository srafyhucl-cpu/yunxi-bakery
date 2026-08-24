"""员工助手 LangGraph 编排测试。"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from app.models.employee_agent import AgentIntent, AgentPlan
from app.service.agents.employee.graph import build_employee_agent_graph
from app.service.agents.employee.nodes import (
    EmployeeAgentNodes,
    EmployeeGraphDependencies,
)
from app.service.agents.employee.service import EmployeeAgentGraphService


class _FakePlanner:
    async def plan(self, query: str) -> AgentPlan:
        return AgentPlan(
            intent=AgentIntent.PRODUCT_QUERY,
            tools=("product_lookup",),
        )


class _FakeBusinessToolService:
    async def lookup_orders(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "订单兜底"}

    async def lookup_products(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "result": f"{payload['query']}｜库存 6",
            "nextAction": "库存和价格以小程序商品数据为准。",
        }

    async def answer_knowledge(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "知识库回复"}


class _FakeOpsToolService:
    async def lookup_customer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "客户线索"}

    async def summarize_group_campaign(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {"ok": True, "result": "客户群汇总"}

    async def list_pending_handoffs(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "待人工"}


class _FakeStatusToolService:
    async def summarize_ops(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "经营摘要"}

    async def summarize_integrations(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "同步状态"}

    async def summarize_offline_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "离线复盘"}


def test_employee_nodes_use_langgraph_tool_node() -> None:
    from app.service.agents.tool_node import load_tool_node_class

    ToolNode = load_tool_node_class()
    nodes = EmployeeAgentNodes(
        EmployeeGraphDependencies(
            business_tool_service=_FakeBusinessToolService(),
            ops_tool_service=_FakeOpsToolService(),
            status_tool_service=_FakeStatusToolService(),
        )
    )

    assert isinstance(nodes._tool_node_instance(), ToolNode)


@pytest.mark.asyncio
async def test_employee_graph_returns_deterministic_tool_reply() -> None:
    service = EmployeeAgentGraphService(
        EmployeeGraphDependencies(
            business_tool_service=_FakeBusinessToolService(),
            ops_tool_service=_FakeOpsToolService(),
            status_tool_service=_FakeStatusToolService(),
            planner=_FakePlanner(),
        )
    )

    reply = await service.answer("草莓蛋糕还有库存吗")

    assert "草莓蛋糕还有库存吗｜库存 6" in reply
    assert "下一步：库存和价格以小程序商品数据为准。" in reply


@pytest.mark.asyncio
async def test_employee_graph_service_can_return_trace_run() -> None:
    service = EmployeeAgentGraphService(
        EmployeeGraphDependencies(
            business_tool_service=_FakeBusinessToolService(),
            ops_tool_service=_FakeOpsToolService(),
            status_tool_service=_FakeStatusToolService(),
            planner=_FakePlanner(),
        )
    )

    reply, trace_run = await service.answer_with_trace("草莓蛋糕还有库存吗")

    assert "草莓蛋糕还有库存吗｜库存 6" in reply
    assert trace_run.agent == "employee"
    assert trace_run.channel == "wecom_employee"
    assert trace_run.final_status == "success"
    assert [event["node"] for event in trace_run.trace_events] == [
        "load_employee_context",
        "plan_intent",
        "select_tools",
        "execute_tools",
        "validate_tool_facts",
        "deterministic_finalizer",
        "record_trace",
    ]


@pytest.mark.asyncio
async def test_employee_graph_trace_events_use_observability_shape() -> None:
    graph = build_employee_agent_graph(
        EmployeeGraphDependencies(
            business_tool_service=_FakeBusinessToolService(),
            ops_tool_service=_FakeOpsToolService(),
            status_tool_service=_FakeStatusToolService(),
            planner=_FakePlanner(),
        )
    )

    result = await graph.ainvoke({"query": "草莓蛋糕还有库存吗"})

    trace_events = result["trace_events"]
    assert [event["node"] for event in trace_events] == [
        "load_employee_context",
        "plan_intent",
        "select_tools",
        "execute_tools",
        "validate_tool_facts",
        "deterministic_finalizer",
        "record_trace",
    ]
    assert all(event["event"] == "node" for event in trace_events)
    assert trace_events[1]["intent"] == "product_query"
    assert trace_events[2]["tool_name"] == "product_lookup"
    assert trace_events[2]["tool_call_count"] == 1
    assert trace_events[3]["count"] == 1
    assert trace_events[3]["tool_name"] == "product_lookup"
    assert trace_events[3]["tool_call_count"] == 1
    assert trace_events[5]["final_status"] == "success"


def test_employee_service_import_does_not_import_langgraph() -> None:
    project_root = Path(__file__).resolve().parents[3]
    command = (
        "import sys; "
        "import app.service.wecom.employee_agent_service; "
        "raise SystemExit(1 if 'langgraph' in sys.modules else 0)"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=project_root,
        check=False,
    )

    assert result.returncode == 0
