"""企微员工助手订单经营洞察文案。"""

from __future__ import annotations

HEAVY_PENDING_THRESHOLD = 5
MEDIUM_PENDING_THRESHOLD = 2


def order_action_overview(
    *,
    total_count: int,
    total_amount_yuan: float,
    pending_count: int,
    risk_count: int,
    refund_count: int,
    missing_logistics_count: int,
) -> list[str]:
    pressure_label = order_pressure_label(pending_count, risk_count)
    return [
        (
            f"今天 {total_count} 单，合计 {total_amount_yuan:.2f} 元；"
            f"发货压力：{pressure_label}。"
        ),
        (
            f"待处理 {pending_count} 单，履约风险 {risk_count} 单，"
            f"退款/售后 {refund_count} 单，无物流 {missing_logistics_count} 单。"
        ),
    ]


def order_priority_heading(
    *,
    risk_count: int,
    pending_count: int,
    missing_logistics_count: int,
    refund_count: int,
) -> str:
    if risk_count:
        return "优先级 1：先处理已过或快到约送时间的履约风险单"
    if pending_count:
        return "优先级 1：先处理待发货/待收货订单"
    if missing_logistics_count:
        return "优先级 1：先核对无物流订单"
    if refund_count:
        return "优先级 1：先核对退款/售后订单"
    return "目前没有必须马上处理的订单事项"


def order_action_next_step(
    *,
    risk_count: int,
    pending_count: int,
    missing_logistics_count: int,
    refund_count: int,
) -> str:
    if risk_count:
        return "先处理履约风险单，再按无物流、退款/售后顺序核对。"
    if pending_count:
        return "先处理待发货/待收货订单，再核对无物流和退款/售后。"
    if missing_logistics_count:
        return "先核对无物流订单，确认是否已发货但未回写。"
    if refund_count:
        return "先核对退款/售后订单，确认是否需要对客回复。"
    return "暂无紧急订单动作，保持观察即可。"


def order_pressure_label(pending_count: int, risk_count: int) -> str:
    if risk_count or pending_count >= HEAVY_PENDING_THRESHOLD:
        return "偏高"
    if pending_count >= MEDIUM_PENDING_THRESHOLD:
        return "中等"
    return "低"
