from __future__ import annotations

from datetime import date

from app.models.employee_agent import AgentIntent, OrderQueryKind
from app.service.wecom.employee_agent_planner import EmployeeAgentPlanner


def _planner() -> EmployeeAgentPlanner:
    return EmployeeAgentPlanner(
        today_provider=lambda: date(2026, 7, 5),
        enable_llm=False,
    )


async def test_planner_uses_effective_statuses_for_completed_summary() -> None:
    plan = await _planner().plan("昨天已完成多少订单")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.SUMMARY
    assert plan.query_plan.date_from == "2026-07-04"
    assert plan.query_plan.date_to == "2026-07-04"
    assert plan.query_plan.statuses == (
        "WAIT_SELLER_SEND_GOODS",
        "WAIT_BUYER_CONFIRM_GOODS",
        "TRADE_SUCCESS",
    )
    assert plan.query_plan.keyword == ""


async def test_planner_keeps_trade_success_query_strict() -> None:
    plan = await _planner().plan("昨天交易成功多少订单")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.SUMMARY
    assert plan.query_plan.statuses == ("TRADE_SUCCESS",)
    assert plan.query_plan.keyword == ""


async def test_planner_maps_preorder_query_to_delivery_pending() -> None:
    plan = await _planner().plan("有没有明天的预定订单")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.LIST
    assert plan.query_plan.date_from == "2026-07-06"
    assert plan.query_plan.date_to == "2026-07-06"
    assert plan.query_plan.date_field == "delivery_time"
    assert plan.query_plan.statuses == (
        "WAIT_SELLER_SEND_GOODS",
        "WAIT_BUYER_CONFIRM_GOODS",
    )
    assert plan.query_plan.keyword == ""


async def test_exact_order_customer_history_query_uses_list_plan() -> None:
    plan = await _planner().plan("E202600000000 这个客户还买过什么")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.LIST
    assert plan.query_plan.keyword == ""


async def test_exact_order_detail_query_keeps_detail_plan() -> None:
    plan = await _planner().plan("查 E202600000000")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.DETAIL
