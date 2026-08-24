"""企微员工助手订单待办概览编排。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.models.employee_agent import OrderQueryKind, OrderQueryPlan, ToolResult
from app.service.wecom.employee_agent_order_constants import ORDER_PENDING_STATUSES
from app.service.wecom.intelligent_bot_order_format import (
    build_order_action_items_tool_result,
)


async def answer_order_action_items(
    repo: Any,
    query: str,
    plan: OrderQueryPlan,
) -> ToolResult:
    """组合既有白名单订单查询，生成今日经营待办概览。"""
    today_summary = await repo.summarize_orders(
        replace(plan, kind=OrderQueryKind.SUMMARY, keyword="", statuses=())
    )
    pending_plan = replace(
        plan,
        kind=OrderQueryKind.LIST,
        keyword="",
        statuses=ORDER_PENDING_STATUSES,
        sort_by="latest",
    )
    risk_plan = replace(
        pending_plan,
        needs_fulfillment_risk=True,
        sort_by="delivery_time",
    )
    refund_plan = replace(
        plan,
        kind=OrderQueryKind.SUMMARY,
        keyword="",
        statuses=(),
        needs_refund=True,
    )
    missing_logistics_plan = replace(
        pending_plan,
        needs_missing_logistics=True,
    )
    pending_summary = await repo.summarize_orders(pending_plan)
    pending_orders = await repo.query_orders(pending_plan)
    risk_orders = await repo.query_orders(risk_plan)
    refund_summary = await repo.summarize_orders(refund_plan)
    missing_logistics_orders = await repo.query_orders(missing_logistics_plan)
    return build_order_action_items_tool_result(
        query,
        today_summary,
        pending_summary,
        pending_orders,
        risk_orders,
        refund_summary,
        missing_logistics_orders,
    )
