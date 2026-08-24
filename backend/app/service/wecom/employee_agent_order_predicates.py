"""企微员工助手订单问法谓词。"""

from __future__ import annotations

from app.service.wecom.employee_agent_order_keywords import (
    ORDER_ACTION_ITEMS_KEYWORDS,
    ORDER_CUSTOMER_HISTORY_KEYWORDS,
    ORDER_FULFILLMENT_RISK_KEYWORDS,
    ORDER_POLICY_KEYWORDS,
    ORDER_PREORDER_DELIVERY_KEYWORDS,
    ORDER_REFUND_KEYWORDS,
)


def needs_missing_logistics(query: str) -> bool:
    """判断是否查询无物流订单。"""
    return any(
        word in query
        for word in ("没物流", "无物流", "暂无物流", "还没物流", "没出物流")
    )


def needs_refund(query: str) -> bool:
    """判断是否查询退款/售后订单数据。"""
    return any(word in query for word in ORDER_REFUND_KEYWORDS) and not (
        _looks_like_pure_policy_query(query)
    )


def needs_fulfillment_risk(query: str) -> bool:
    """判断是否查询履约风险订单。"""
    return any(word in query for word in ORDER_FULFILLMENT_RISK_KEYWORDS)


def needs_action_items(query: str) -> bool:
    """判断是否查询今日经营待办概览。"""
    return any(word in query for word in ORDER_ACTION_ITEMS_KEYWORDS)


def needs_preorder_delivery(query: str) -> bool:
    """判断是否在问约送/预定待处理订单。"""
    return any(word in query for word in ORDER_PREORDER_DELIVERY_KEYWORDS)


def has_customer_history_intent(query: str) -> bool:
    """判断是否在问某个客户的历史订单。"""
    return any(word in query for word in ORDER_CUSTOMER_HISTORY_KEYWORDS)


def looks_like_order_policy_query(query: str) -> bool:
    """判断是否退款规则、话术或政策类知识问法。"""
    return any(word in query for word in ORDER_POLICY_KEYWORDS) and (
        _looks_like_pure_policy_query(query)
    )


def looks_like_knowledge_followup_query(query: str) -> bool:
    """判断是否需要在数据结果后补充规则或话术。"""
    return any(word in query for word in ORDER_POLICY_KEYWORDS)


def _looks_like_pure_policy_query(query: str) -> bool:
    data_words = (
        "订单",
        "单子",
        "哪些",
        "今天",
        "本周",
        "这周",
        "最近",
        "多少",
        "几单",
        "待发货",
        "没发货",
        "未发货",
        "退款订单",
        "退款单",
        "退单",
    )
    return not any(word in query for word in data_words)


def resolve_sort_by(query: str) -> str:
    """解析订单查询排序口径。"""
    if needs_fulfillment_risk(query):
        return "delivery_time"
    return "amount" if "金额" in query else "latest"
