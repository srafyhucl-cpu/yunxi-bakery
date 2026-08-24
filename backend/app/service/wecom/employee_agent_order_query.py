"""企微员工助手订单查询计划解析。"""

from __future__ import annotations

import re
from datetime import date

from app.models.employee_agent import AnswerStyle, OrderQueryKind, OrderQueryPlan
from app.service.wecom.employee_agent_order_date import (
    resolve_order_date_field,
    resolve_order_date_range,
)
from app.service.wecom.employee_agent_order_delivery_time import (
    resolve_delivery_time_window,
)
from app.service.wecom.employee_agent_order_constants import (
    DEFAULT_RESULT_LIMIT,
    MAX_RESULT_LIMIT,
    ORDER_NO_PATTERN,
)
from app.service.wecom.employee_agent_order_keyword_extract import (
    extract_order_keyword,
)
from app.service.wecom.employee_agent_order_keywords import (
    ORDER_QUERY_KEYWORDS,
    ORDER_REVENUE_KEYWORDS,
)
from app.service.wecom.employee_agent_order_predicates import (
    looks_like_order_policy_query,
    looks_like_knowledge_followup_query,
    needs_action_items,
    has_customer_history_intent,
    needs_fulfillment_risk,
    needs_missing_logistics,
    needs_refund,
    resolve_sort_by,
)
from app.service.wecom.employee_agent_order_status import resolve_order_statuses


def has_exact_order_no(query: str) -> bool:
    return bool(ORDER_NO_PATTERN.search(query))


def build_order_query_plan(
    query: str,
    today: date,
    kind: OrderQueryKind,
) -> OrderQueryPlan:
    date_from, date_to = resolve_order_date_range(query, today)
    delivery_time_window = resolve_delivery_time_window(query)
    has_date_range = bool(date_from or date_to)
    return OrderQueryPlan(
        kind=kind,
        date_from=date_from,
        date_to=date_to,
        date_field=resolve_order_date_field(query),
        statuses=resolve_order_statuses(query, has_date_range=has_date_range),
        keyword=""
        if kind == OrderQueryKind.ACTION_ITEMS or has_customer_history_intent(query)
        else extract_order_keyword(query),
        needs_missing_logistics=needs_missing_logistics(query),
        needs_refund=needs_refund(query),
        needs_fulfillment_risk=needs_fulfillment_risk(query),
        delivery_time_start=delivery_time_window.start if delivery_time_window else "",
        delivery_time_end=delivery_time_window.end if delivery_time_window else "",
        aggregate_by="product" if kind == OrderQueryKind.TOP_PRODUCTS else "",
        sort_by=resolve_sort_by(query),
        limit=_extract_limit(query),
    )


def resolve_order_kind(query: str) -> OrderQueryKind:
    if needs_action_items(query):
        return OrderQueryKind.ACTION_ITEMS
    if any(word in query for word in ("卖得最多", "卖最多", "销量", "卖得多", "卖爆")):
        return OrderQueryKind.TOP_PRODUCTS
    if any(word in query for word in ORDER_REVENUE_KEYWORDS):
        return OrderQueryKind.SUMMARY
    if needs_refund(query):
        return OrderQueryKind.SUMMARY
    if needs_fulfillment_risk(query):
        return OrderQueryKind.LIST
    if any(word in query for word in ("多少", "几单", "一共", "统计", "总共", "单量")):
        return OrderQueryKind.SUMMARY
    if any(word in query for word in ("详情", "具体", "订单号")):
        return OrderQueryKind.DETAIL
    return OrderQueryKind.LIST


def answer_style_for_order_kind(kind: OrderQueryKind) -> AnswerStyle:
    if kind == OrderQueryKind.ACTION_ITEMS:
        return AnswerStyle.ACTION_ITEMS
    if kind == OrderQueryKind.LIST:
        return AnswerStyle.LIST
    if kind == OrderQueryKind.DETAIL:
        return AnswerStyle.DETAIL
    return AnswerStyle.SUMMARY


def extract_limit_from_value(value: object) -> int:
    """从 LLM 计划值中提取安全 limit。"""
    if isinstance(value, int):
        return max(1, min(value, MAX_RESULT_LIMIT))
    return _extract_limit(str(value or ""))


def looks_like_order_query(query: str) -> bool:
    if looks_like_order_policy_query(query):
        return False
    return any(word in query for word in ORDER_QUERY_KEYWORDS)


def looks_like_inventory_query(query: str) -> bool:
    return any(word in query for word in ("库存", "还够", "够吗", "还有吗"))


def looks_like_order_knowledge_query(query: str) -> bool:
    return looks_like_knowledge_followup_query(query)


def _extract_limit(query: str) -> int:
    match = re.search(r"(\d+)\s*(?:条|个|单)", query)
    if not match:
        return DEFAULT_RESULT_LIMIT
    return max(1, min(int(match.group(1)), MAX_RESULT_LIMIT))
