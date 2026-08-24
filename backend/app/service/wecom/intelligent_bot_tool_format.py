"""企微智能机器人工具展示格式化。"""

from typing import Any

from app.service.wecom.intelligent_bot_product_filter import (
    compact_product,
    filter_products,
    is_featured_query,
)

__all__ = [
    "compact_knowledge_entry",
    "compact_order",
    "compact_product",
    "filter_products",
    "is_featured_query",
    "knowledge_line",
    "mask_phone",
    "order_line",
    "product_line",
    "snippet",
]

MAX_SNIPPET_LENGTH = 140
PHONE_MASK_PREFIX_LENGTH = 3
PHONE_MASK_SUFFIX_LENGTH = 4
PHONE_MASK_LENGTH = 11


def compact_order(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(order.get("id", "")),
        "status": str(order.get("status", "")),
        "paymentStatus": str(order.get("paymentStatus", "")),
        "itemTitle": str(order.get("itemTitle", "")),
        "itemCount": int(order.get("itemCount", 0) or 0),
        "totalFen": int(order.get("totalFen", 0) or 0),
        "receiverName": str(order.get("receiverName", "")),
        "receiverPhoneMasked": mask_phone(str(order.get("receiverPhone", ""))),
        "expectTime": str(order.get("expectTime", "")),
        "createdAt": str(order.get("createdAt", "")),
    }


def compact_knowledge_entry(entry: Any) -> dict[str, Any]:
    return {
        "id": int(getattr(entry, "id", 0) or 0),
        "title": str(getattr(entry, "title", "")),
        "category": str(getattr(entry, "category", "")),
        "snippet": snippet(str(getattr(entry, "content", ""))),
    }


def mask_phone(phone: str) -> str:
    if len(phone) != PHONE_MASK_LENGTH or not phone.isdigit():
        return ""
    return phone[:PHONE_MASK_PREFIX_LENGTH] + "****" + phone[-PHONE_MASK_SUFFIX_LENGTH:]


def snippet(content: str) -> str:
    compact_content = " ".join(content.split())
    if len(compact_content) <= MAX_SNIPPET_LENGTH:
        return compact_content
    return f"{compact_content[:MAX_SNIPPET_LENGTH]}..."


def order_line(order: dict[str, Any]) -> str:
    total_yuan = order["totalFen"] / 100
    return (
        f"{order['id']}｜{order['status']}｜{order['paymentStatus']}｜"
        f"{order['itemTitle']} x {order['itemCount']}｜{total_yuan:.2f}元"
    )


def product_line(product: dict[str, Any]) -> str:
    price_yuan = product["priceFen"] / 100
    return (
        f"{product['title']}｜{price_yuan:.2f}元｜库存 {product['stock']}｜"
        f"{product['categoryName'] or '未分类'}"
    )


def knowledge_line(source: dict[str, Any]) -> str:
    return f"{source['title']}：{source['snippet']}"
