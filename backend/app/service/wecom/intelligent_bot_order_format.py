"""企微智能机器人订单展示格式。"""

from __future__ import annotations

import re
from typing import Any

from app.models.employee_agent import OrderQueryPlan, ToolResult
from app.service.wecom.intelligent_bot_delivery_format import (
    employee_delivery_time_text as employee_delivery_time_text,
)
from app.service.wecom.intelligent_bot_order_empty_format import (
    empty_order_list_text,
    empty_order_next_action,
)
from app.service.wecom.intelligent_bot_order_insights import (
    order_action_next_step,
    order_action_overview,
    order_priority_heading,
    order_pressure_label,
)
from app.service.wecom.intelligent_bot_top_products_format import (
    build_top_products_tool_result as build_top_products_tool_result,
)

ORDER_STATUS_LABELS = {
    "WAIT_BUYER_PAY": "待付款",
    "WAIT_SELLER_SEND_GOODS": "待发货",
    "WAIT_BUYER_CONFIRM_GOODS": "待收货",
    "TRADE_SUCCESS": "交易成功",
    "TRADE_CLOSED": "已关闭",
    "TRADE_PAID": "已付款",
}


def build_order_summary_tool_result(
    query: str,
    summary: dict[str, Any],
    orders: list[dict[str, Any]],
) -> ToolResult:
    """构造员工可读订单统计结果。"""
    total_count = int(summary.get("total_count", 0) or 0)
    total_amount_yuan = int(summary.get("total_amount_fen", 0) or 0) / 100
    status_text = status_counts_text(summary.get("status_counts", {}))
    recent_lines = [
        employee_order_line(index, order) for index, order in enumerate(orders, 1)
    ]
    lines = [
        f"{query}：共 {total_count} 单，合计 {total_amount_yuan:.2f} 元。",
        status_text,
    ]
    if recent_lines:
        lines.append("最近相关订单：")
        lines.extend(recent_lines)
    return ToolResult(
        ok=True,
        summary="\n".join(line for line in lines if line),
        items=[compact_employee_order(order) for order in orders],
        metrics=summary,
        next_action="如需看某一单详情，可带订单尾号继续追问。",
    )


def build_order_list_tool_result(
    query: str,
    summary: dict[str, Any],
    orders: list[dict[str, Any]],
    plan: OrderQueryPlan | None = None,
) -> ToolResult:
    """构造员工可读订单列表结果。"""
    if not orders:
        return ToolResult(
            ok=True,
            summary=f"{query}：{empty_order_list_text(plan)}",
            metrics=summary,
            next_action=empty_order_next_action(plan),
        )
    lines = [_order_list_heading(query, len(orders), plan)]
    if _looks_like_fulfillment_pressure_query(query):
        lines.append(_fulfillment_pressure_line(summary, orders))
    lines.extend(
        employee_order_line(index, order) for index, order in enumerate(orders, 1)
    )
    return ToolResult(
        ok=True,
        summary="\n".join(lines),
        items=[compact_employee_order(order) for order in orders],
        metrics=summary,
        next_action=_order_list_next_action(plan),
    )


def build_order_action_items_tool_result(
    query: str,
    today_summary: dict[str, Any],
    pending_summary: dict[str, Any],
    pending_orders: list[dict[str, Any]],
    risk_orders: list[dict[str, Any]],
    refund_summary: dict[str, Any],
    missing_logistics_orders: list[dict[str, Any]],
) -> ToolResult:
    """构造今日订单经营待办结果。"""
    total_count = int(today_summary.get("total_count", 0) or 0)
    total_amount_yuan = int(today_summary.get("total_amount_fen", 0) or 0) / 100
    pending_count = int(pending_summary.get("total_count", 0) or 0)
    refund_count = int(refund_summary.get("total_count", 0) or 0)
    risk_count = len(risk_orders)
    missing_logistics_count = len(missing_logistics_orders)
    lines = [f"{query}："]
    lines.extend(
        order_action_overview(
            total_count=total_count,
            total_amount_yuan=total_amount_yuan,
            pending_count=pending_count,
            risk_count=risk_count,
            refund_count=refund_count,
            missing_logistics_count=missing_logistics_count,
        )
    )
    lines.append(
        order_priority_heading(
            risk_count=risk_count,
            pending_count=pending_count,
            missing_logistics_count=missing_logistics_count,
            refund_count=refund_count,
        )
    )
    if risk_orders:
        lines.extend(_limited_order_lines(risk_orders))
    elif pending_orders:
        lines.extend(_limited_order_lines(pending_orders))
    if missing_logistics_orders:
        lines.append("优先级 2：核对无物流订单")
        lines.extend(_limited_order_lines(missing_logistics_orders))
    next_action = order_action_next_step(
        risk_count=risk_count,
        pending_count=pending_count,
        missing_logistics_count=missing_logistics_count,
        refund_count=refund_count,
    )
    return ToolResult(
        ok=True,
        summary="\n".join(lines),
        items=[compact_employee_order(order) for order in pending_orders],
        metrics={
            "total_count": total_count,
            "total_amount_fen": int(today_summary.get("total_amount_fen", 0) or 0),
            "pending_count": pending_count,
            "fulfillment_risk_count": risk_count,
            "refund_count": refund_count,
            "missing_logistics_count": missing_logistics_count,
        },
        next_action=next_action,
    )


def status_counts_text(status_counts: Any) -> str:
    """格式化订单状态分布。"""
    if not isinstance(status_counts, dict) or not status_counts:
        return ""
    parts = [
        f"{ORDER_STATUS_LABELS.get(status, status)} {count} 单"
        for status, count in status_counts.items()
    ]
    return "状态分布：" + "，".join(parts) + "。"


def _limited_order_lines(orders: list[dict[str, Any]]) -> list[str]:
    return [employee_order_line(index, order) for index, order in enumerate(orders, 1)]


def _looks_like_fulfillment_pressure_query(query: str) -> bool:
    return "发货压力" in query or "履约压力" in query


def _order_list_heading(
    query: str,
    order_count: int,
    plan: OrderQueryPlan | None,
) -> str:
    if plan is not None and plan.needs_fulfillment_risk:
        return f"{query}：找到 {order_count} 单，按约送时间从早到晚展示："
    return f"{query}：找到 {order_count} 单，按最新订单展示："


def _order_list_next_action(plan: OrderQueryPlan | None) -> str:
    if plan is not None and plan.needs_fulfillment_risk:
        return "先处理已过约送时间或暂无物流的履约风险单；排查时可用尾号继续追问。"
    return "列表默认只展示订单尾号，排查时可用尾号继续追问。"


def _fulfillment_pressure_line(
    summary: dict[str, Any],
    orders: list[dict[str, Any]],
) -> str:
    pending_count = int(summary.get("total_count", len(orders)) or 0)
    risk_count = len(orders)
    pressure_label = order_pressure_label(pending_count, risk_count)
    return (
        f"发货压力：{pressure_label}。"
        f"待处理 {pending_count} 单，履约风险 {risk_count} 单。"
    )


def employee_order_line(index: int, order: dict[str, Any]) -> str:
    """格式化员工列表中的单行订单。"""
    amount_yuan = int(order.get("amount_fen", 0) or 0) / 100
    order_tail = order_tail_text(str(order.get("order_no", "")))
    status_label = ORDER_STATUS_LABELS.get(
        str(order.get("status", "")), str(order.get("status", ""))
    )
    pay_time = str(order.get("pay_time") or order.get("created_at") or "未记录时间")
    delivery_text = employee_delivery_time_text(order)
    logistics_text = employee_logistics_text(order)
    refund_text = employee_refund_text(order)
    product_titles = str(order.get("product_titles") or "未记录商品")
    return (
        f"{index}. 尾号 {order_tail}｜{status_label}｜{product_titles}｜"
        f"{amount_yuan:.2f} 元｜{pay_time}｜{delivery_text}｜"
        f"{logistics_text}{refund_text}"
    )


def compact_employee_order(order: dict[str, Any]) -> dict[str, Any]:
    """压缩订单字段，避免暴露完整订单和隐私字段。"""
    return {
        "orderTail": order_tail_text(str(order.get("order_no", ""))),
        "status": ORDER_STATUS_LABELS.get(
            str(order.get("status", "")), str(order.get("status", ""))
        ),
        "productTitles": str(order.get("product_titles", "")),
        "amountFen": int(order.get("amount_fen", 0) or 0),
        "payTime": str(order.get("pay_time") or order.get("created_at") or ""),
        "deliveryTime": str(order.get("delivery_time") or ""),
        "logisticsStatus": employee_logistics_text(order),
        "refundStatus": employee_refund_text(order).lstrip("｜"),
    }


def order_tail_text(order_no: str) -> str:
    """只展示订单尾号。"""
    return order_no[-6:] if len(order_no) > 6 else order_no


def employee_logistics_text(order: dict[str, Any]) -> str:
    """格式化员工可读物流状态。"""
    logistics_status = str(order.get("logistics_status") or "")
    logistics_no = str(order.get("logistics_no") or "")
    if logistics_status:
        return logistics_status
    if logistics_no:
        return "有物流单号"
    return "暂无物流"


def employee_refund_text(order: dict[str, Any]) -> str:
    """格式化员工可读退款标记。"""
    try:
        refund_state = int(order.get("refund_state", 0) or 0)
    except (TypeError, ValueError):
        refund_state = 0
    return "｜有退款/售后" if refund_state else ""


def youzan_order_line(order: dict[str, Any]) -> str:
    """格式化有赞订单搜索结果。"""
    amount_yuan = order["amountFen"] / 100
    quantity = order.get("totalQuantity", 0)
    quantity_text = (
        f" x {quantity}"
        if quantity and not product_title_has_quantity(order["productTitles"])
        else ""
    )
    logistics_text = (
        order.get("logisticsStatus") or order.get("logisticsNo") or "暂无物流"
    )
    return (
        f"{order['orderNo']}｜{order['status']}｜{order['productTitles']}{quantity_text}｜"
        f"{amount_yuan:.2f}元｜{order.get('payTime') or '未记录付款时间'}｜{logistics_text}"
    )


def youzan_order_detail_line(order: dict[str, Any]) -> str:
    """格式化有赞订单详情。"""
    amount_yuan = order["amountFen"] / 100
    logistics_text = (
        order.get("logisticsStatus") or order.get("logisticsNo") or "暂无物流"
    )
    message = order.get("message")
    if message and not order.get("productTitles"):
        if logistics_text != "暂无物流":
            return f"{order['orderNo']}｜{logistics_text}"
        return f"{order['orderNo']}｜{message}"
    return (
        f"{order['orderNo']}｜{order['status']}｜{order.get('productTitles', '')}｜"
        f"{amount_yuan:.2f}元｜配送 {order.get('deliveryArea') or '未记录'}｜{logistics_text}"
    )


def product_title_has_quantity(product_titles: str) -> bool:
    """判断商品标题是否已经包含数量。"""
    return bool(re.search(r"(?:x|×)\s*\d+", product_titles, re.IGNORECASE))
