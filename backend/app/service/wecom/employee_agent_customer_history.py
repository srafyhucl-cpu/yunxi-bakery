"""企微员工助手按客户历史订单查询辅助。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.models.employee_agent import OrderQueryPlan, ToolResult
from app.service.wecom.employee_agent_order_constants import ORDER_NO_PATTERN
from app.service.wecom.employee_agent_order_predicates import (
    has_customer_history_intent,
)

CUSTOMER_HISTORY_QUERY_LABEL = "该客户历史订单"


async def resolve_customer_history_plan(
    query: str,
    plan: OrderQueryPlan,
    youzan_order_repo: Any,
) -> tuple[OrderQueryPlan | None, ToolResult | None, str]:
    """把带 E 号的客户历史单问法解析成 buyer_id 过滤。"""
    if not has_customer_history_intent(query):
        return plan, None, query
    order_no = extract_order_no(query)
    if not order_no:
        return (
            None,
            ToolResult(
                ok=False,
                summary="未识别到有效的有赞交易号，暂时无法继续查询该客户历史订单。",
                next_action="请带一个 E 开头的有赞交易号继续追问该客户历史单。",
            ),
            CUSTOMER_HISTORY_QUERY_LABEL,
        )
    order = await youzan_order_repo.get_by_order_no(order_no)
    if not order:
        return (
            None,
            ToolResult(
                ok=False,
                summary="未找到该交易号，无法继续查询该客户历史订单。",
                next_action="请先确认 E 开头的有赞交易号是否正确，再继续追问该客户历史单。",
            ),
            CUSTOMER_HISTORY_QUERY_LABEL,
        )
    buyer_id = str(order.get("buyer_id") or "").strip()
    if not buyer_id:
        return (
            None,
            ToolResult(
                ok=False,
                summary="该交易号缺少客户标识，暂时无法继续查询该客户历史订单。",
                next_action="请先到后台核对该订单详情。",
            ),
            CUSTOMER_HISTORY_QUERY_LABEL,
        )
    return replace(plan, buyer_id=buyer_id), None, CUSTOMER_HISTORY_QUERY_LABEL


def extract_order_no(query: str) -> str:
    """从员工原话中提取 E 开头有赞交易号。"""
    match = ORDER_NO_PATTERN.search(query)
    return match.group(0).upper() if match else ""
