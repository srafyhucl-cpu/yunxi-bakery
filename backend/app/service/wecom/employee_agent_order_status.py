"""企微员工助手订单状态语义解析。"""

from __future__ import annotations

from app.service.wecom.employee_agent_order_constants import (
    ORDER_EFFECTIVE_STATUSES,
    ORDER_PENDING_STATUSES,
    ORDER_STATUS_KEYWORDS,
)
from app.service.wecom.employee_agent_order_predicates import (
    needs_fulfillment_risk,
    needs_preorder_delivery,
)

WEAK_COMPLETED_KEYWORDS = ("已完成", "完成")
STRICT_COMPLETED_KEYWORDS = ("交易成功",)


def resolve_order_statuses(
    query: str,
    *,
    has_date_range: bool,
) -> tuple[str, ...]:
    """按员工口语语义解析订单状态过滤。"""
    if needs_fulfillment_risk(query) or "待处理" in query:
        return ORDER_PENDING_STATUSES
    explicit_statuses = _explicit_statuses(query)
    if _should_use_effective_statuses(query, has_date_range, explicit_statuses):
        return ORDER_EFFECTIVE_STATUSES
    if explicit_statuses:
        return explicit_statuses
    if needs_preorder_delivery(query):
        return ORDER_PENDING_STATUSES
    return ()


def _explicit_statuses(query: str) -> tuple[str, ...]:
    statuses = [
        status
        for status, keywords in ORDER_STATUS_KEYWORDS.items()
        if any(keyword in query for keyword in keywords)
    ]
    return tuple(dict.fromkeys(statuses))


def _should_use_effective_statuses(
    query: str,
    has_date_range: bool,
    explicit_statuses: tuple[str, ...],
) -> bool:
    return (
        has_date_range
        and explicit_statuses == ("TRADE_SUCCESS",)
        and any(keyword in query for keyword in WEAK_COMPLETED_KEYWORDS)
        and not any(keyword in query for keyword in STRICT_COMPLETED_KEYWORDS)
    )
