"""企微订单查询编排辅助函数。"""

from __future__ import annotations

import re
from typing import Any

from app.utils import yuan_to_fen

LOGISTICS_KEYWORDS = ("物流", "配送", "发货", "送到", "快递", "轨迹")
RECENT_ORDER_KEYWORDS = ("最近", "最新", "近几单", "这几单")
ORDER_QUERY_STOP_WORDS = (
    "帮我",
    "查一下",
    "查询",
    "查",
    "订单号",
    "订单",
    "下单记录",
    "下单",
)
YOUZAN_ORDER_NO_PATTERN = re.compile(r"\bE\d{12,}\b", re.IGNORECASE)


def extract_youzan_order_no(query: str) -> str:
    """提取 E 开头有赞交易号。"""
    match = YOUZAN_ORDER_NO_PATTERN.search(query)
    return match.group(0).upper() if match else ""


def is_logistics_query(query: str) -> bool:
    """判断是否在问物流。"""
    return any(keyword in query for keyword in LOGISTICS_KEYWORDS)


def is_recent_order_query(query: str) -> bool:
    """判断是否在问最近订单。"""
    return any(keyword in query for keyword in RECENT_ORDER_KEYWORDS)


def normalize_search_keyword(query: str) -> str:
    """去除通用订单词，保留主要检索词。"""
    keyword = query.strip()
    for stop_word in ORDER_QUERY_STOP_WORDS:
        keyword = keyword.replace(stop_word, " ")
    compact_keyword = " ".join(keyword.split())
    return compact_keyword or query.strip()


def compact_live_order(order: dict[str, Any], order_no: str) -> dict[str, Any]:
    """压缩实时工具返回的订单详情。"""
    return {
        "source": str(order.get("source", "youzan_live")),
        "orderNo": str(order.get("order_no") or order_no),
        "status": str(order.get("status") or order.get("status_str") or ""),
        "amountFen": yuan_to_fen(order.get("amount_yuan")),
        "productTitles": str(order.get("product_titles", "")),
        "payTime": str(order.get("pay_time", "")),
        "deliveryArea": join_area(
            order.get("delivery_province"),
            order.get("delivery_city"),
            order.get("delivery_district"),
        ),
        "deliveryTime": str(order.get("delivery_time", "")),
        "logisticsNo": str(order.get("logistics_no") or order.get("express_id") or ""),
        "logisticsStatus": latest_logistics_status(order),
        "message": str(order.get("message", "")),
    }


def compact_youzan_order(order: dict[str, Any]) -> dict[str, Any]:
    """压缩仓库层有赞订单结果。"""
    return {
        "source": "youzan_orders",
        "orderNo": str(order.get("order_no", "")),
        "status": str(order.get("status", "")),
        "amountFen": int(order.get("amount_fen", 0) or 0),
        "productTitles": str(order.get("product_titles", "")),
        "totalQuantity": int(order.get("total_quantity", 0) or 0),
        "payTime": str(order.get("pay_time", "")),
        "deliveryArea": join_area(
            order.get("delivery_province"),
            order.get("delivery_city"),
            order.get("delivery_district"),
        ),
        "deliveryTime": str(order.get("delivery_time", "")),
        "logisticsNo": str(order.get("logistics_no", "")),
        "logisticsStatus": str(order.get("logistics_status", "")),
        "refundState": int(order.get("refund_state", 0) or 0),
    }


def join_area(*parts: object) -> str:
    """拼接配送区域。"""
    return "".join(str(part) for part in parts if part)


def latest_logistics_status(order: dict[str, Any]) -> str:
    """抽取最新物流状态。"""
    steps = order.get("steps")
    if isinstance(steps, list) and steps:
        return str(steps[0])
    return str(order.get("logistics_status", ""))
