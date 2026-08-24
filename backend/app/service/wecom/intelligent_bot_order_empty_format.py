"""企微员工订单空结果展示格式。"""

from __future__ import annotations

from app.models.employee_agent import OrderQueryPlan

ORDER_STATUS_LABELS = {
    "WAIT_BUYER_PAY": "待付款",
    "WAIT_SELLER_SEND_GOODS": "待发货",
    "WAIT_BUYER_CONFIRM_GOODS": "待收货",
    "TRADE_SUCCESS": "交易成功",
    "TRADE_CLOSED": "已关闭",
    "TRADE_PAID": "已付款",
}

PENDING_ORDER_STATUSES = {
    "WAIT_SELLER_SEND_GOODS",
    "WAIT_BUYER_CONFIRM_GOODS",
}


def empty_order_list_text(plan: OrderQueryPlan | None) -> str:
    if plan is None:
        return "没有查到匹配订单。"
    parts = _order_query_scope_parts(plan)
    scope_text = "、".join(parts) if parts else "当前条件"
    return f"没有查到{scope_text}的订单。"


def empty_order_next_action(plan: OrderQueryPlan | None) -> str:
    if plan is None:
        return "如需继续排查，可补充订单尾号、商品名或更明确的业务条件。"
    if plan.date_field == "delivery_time":
        return "这表示当前约送口径下暂无待处理订单；可继续问其他日期或查看今日待办。"
    return "这表示当前查询口径下暂无匹配订单；可继续问其他日期、商品或状态。"


def _order_query_scope_parts(plan: OrderQueryPlan) -> list[str]:
    parts: list[str] = []
    date_scope = _date_scope_text(plan)
    if date_scope:
        parts.append(date_scope)
    if plan.delivery_time_start or plan.delivery_time_end:
        parts.append(_delivery_window_text(plan))
    if plan.statuses:
        parts.append(_status_scope_text(plan.statuses))
    if plan.needs_missing_logistics:
        parts.append("无物流")
    if plan.needs_fulfillment_risk:
        parts.append("履约风险")
    if plan.keyword:
        parts.append(f"商品关键词“{plan.keyword}”")
    return [part for part in parts if part]


def _date_scope_text(plan: OrderQueryPlan) -> str:
    if not plan.date_from and not plan.date_to:
        return ""
    date_label = "约送日期" if plan.date_field == "delivery_time" else "下单日期"
    if plan.date_from and plan.date_from == plan.date_to:
        return f"{date_label} {plan.date_from}"
    if plan.date_from and plan.date_to:
        return f"{date_label} {plan.date_from} 至 {plan.date_to}"
    return f"{date_label} {plan.date_from or plan.date_to}"


def _delivery_window_text(plan: OrderQueryPlan) -> str:
    start = plan.delivery_time_start or "开始"
    end = plan.delivery_time_end or "结束"
    return f"约送时间 {start}-{end}"


def _status_scope_text(statuses: tuple[str, ...]) -> str:
    labels = [ORDER_STATUS_LABELS.get(status, status) for status in statuses]
    if set(statuses) == PENDING_ORDER_STATUSES:
        return "待处理"
    return "、".join(labels)
