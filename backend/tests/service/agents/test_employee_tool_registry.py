"""员工助手 LangChain 工具注册表测试。"""

import json

import pytest

from app.service.agents.tools.employee import EmployeeToolContext


class FakeBusinessToolService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def lookup_orders(self, payload: dict) -> dict:
        self.calls.append(("lookup_orders", payload))
        return {"tool": "order_dynamic_query", "result": "订单结果"}

    async def lookup_products(self, payload: dict) -> dict:
        self.calls.append(("lookup_products", payload))
        return {"tool": "product_lookup", "result": "商品结果"}

    async def answer_knowledge(self, payload: dict) -> dict:
        self.calls.append(("answer_knowledge", payload))
        return {"tool": "knowledge_answer", "result": "知识结果"}


class FakeOpsToolService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def list_pending_handoffs(self, payload: dict) -> dict:
        self.calls.append(("list_pending_handoffs", payload))
        return {"tool": "handoff_pending", "result": "待人工结果"}

    async def lookup_customer(self, payload: dict) -> dict:
        self.calls.append(("lookup_customer", payload))
        return {"tool": "customer_lookup", "result": "客户结果"}

    async def summarize_group_campaign(self, payload: dict) -> dict:
        self.calls.append(("summarize_group_campaign", payload))
        return {"tool": "group_campaign_summary", "result": "客户群结果"}


class FakeStatusToolService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def summarize_ops(self, payload: dict) -> dict:
        self.calls.append(("summarize_ops", payload))
        return {"tool": "ops_summary", "result": "观察台结果"}

    async def summarize_integrations(self, payload: dict) -> dict:
        self.calls.append(("summarize_integrations", payload))
        return {"tool": "integration_status", "result": "同步结果"}

    async def summarize_offline_review(self, payload: dict) -> dict:
        self.calls.append(("summarize_offline_review", payload))
        return {"tool": "offline_review_summary", "result": "复盘结果"}


def test_employee_tool_names_match_capability_contracts() -> None:
    from app.service.agents.tools.registry import build_tools
    from app.service.wecom.employee_agent_capability_contracts import (
        capability_contracts_by_name,
    )

    tools = build_tools("employee", employee_context=EmployeeToolContext())

    assert {tool.name for tool in tools} == set(capability_contracts_by_name())
    assert all(tool.return_direct for tool in tools)


@pytest.mark.asyncio
async def test_employee_tools_call_existing_services() -> None:
    from app.service.agents.tools.registry import build_tools

    business = FakeBusinessToolService()
    ops = FakeOpsToolService()
    status = FakeStatusToolService()
    tools = {
        tool.name: tool
        for tool in build_tools(
            "employee",
            employee_context=EmployeeToolContext(
                business_tool_service=business,
                ops_tool_service=ops,
                status_tool_service=status,
            ),
        )
    }

    order_result = await tools["order_dynamic_query"].ainvoke(
        {"query": "今天订单", "limit": 3}
    )
    campaign_result = await tools["group_campaign_summary"].ainvoke(
        {"campaign_id": "abc123", "limit": 2}
    )
    review_result = await tools["offline_review_summary"].ainvoke({"limit": 1})

    assert json.loads(order_result) == {
        "tool": "order_dynamic_query",
        "result": "订单结果",
    }
    assert json.loads(campaign_result) == {
        "tool": "group_campaign_summary",
        "result": "客户群结果",
    }
    assert json.loads(review_result) == {
        "tool": "offline_review_summary",
        "result": "复盘结果",
    }
    assert business.calls == [("lookup_orders", {"query": "今天订单", "limit": 3})]
    assert ops.calls == [
        ("summarize_group_campaign", {"campaignId": "abc123", "limit": 2})
    ]
    assert status.calls == [("summarize_offline_review", {"limit": 1})]


@pytest.mark.asyncio
async def test_employee_tool_without_service_returns_unavailable() -> None:
    from app.service.agents.tools.registry import build_tools

    tools = {
        tool.name: tool
        for tool in build_tools("employee", employee_context=EmployeeToolContext())
    }
    result = await tools["product_lookup"].ainvoke({"query": "草莓蛋糕"})

    assert json.loads(result) == {
        "tool": "product_lookup",
        "status": "unavailable",
        "result": "商品库存查询暂不可用",
    }
