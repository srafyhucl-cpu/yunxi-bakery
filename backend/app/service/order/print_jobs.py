"""订单小票排版。

58mm 热敏纸按 32 个显示字符宽度换行；中文、全角字符占 2 宽度。
蛋糕联只进裱花间，日常联只包含日常现烤/配送商品；订单同时包含两类时出两张。
"""

import json
import unicodedata

from app.models.order import Order
from app.models.print_job import PrintTicket, PrintTicketType
from app.service.order.fulfillment_types import (
    FULFILLMENT_PREORDER_CAKE,
    classify_fulfillment_type,
)

DEFAULT_TICKET_WIDTH = 32
CAKE_TICKET_TITLE = "【裱花间制作联】"
DAILY_TICKET_TITLE = "【日常现烤/配送联】"
FULFILLMENT_LABELS = {
    "pickup": "到店自提",
    "beijing_delivery": "同城闪送",
    "delivery": "同城闪送",
}
PAYMENT_LABELS = {
    "paid": "已支付",
    "unpaid": "未支付",
    "partial": "部分支付",
    "refunded": "已退款",
    "expired": "已关闭",
}


def _char_width(char: str) -> int:
    """按东亚字符宽度计算显示宽度。"""
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def wrap_display_width(text: str, width: int = DEFAULT_TICKET_WIDTH) -> list[str]:
    """按显示宽度换行，保证每行不超过 width。

    显式换行符保留为空行；超宽中文不会被截断，而是在行边界整体换到下一行。
    """
    if width <= 0:
        raise ValueError("小票宽度必须大于 0")
    lines: list[str] = []
    for raw_line in str(text).splitlines():
        current: list[str] = []
        current_width = 0
        for char in raw_line:
            char_width = _char_width(char)
            if current and current_width + char_width > width:
                lines.append("".join(current))
                current = []
                current_width = 0
            current.append(char)
            current_width += char_width
        lines.append("".join(current))
    return lines


def _append_line(lines: list[str], text: str, width: int) -> None:
    """写入一行并按宽度换行，空字符串不产生内容行。"""
    if not text:
        return
    lines.extend(wrap_display_width(text, width))


def _append_kv(lines: list[str], label: str, value: object, width: int) -> None:
    """写入“标签: 值”，空值跳过。"""
    text = str(value or "").strip()
    if text:
        _append_line(lines, f"{label}: {text}", width)


def _parse_products(raw: str) -> list[dict]:
    """解析订单商品 JSON，空值或非法结构直接报错。"""
    if not str(raw or "").strip():
        raise ValueError("订单商品 JSON 为空")
    try:
        products = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("订单商品 JSON 非法") from exc
    if not isinstance(products, list):
        raise ValueError("订单商品 JSON 必须是数组")
    valid_items = [item for item in products if isinstance(item, dict)]
    if not valid_items:
        raise ValueError("订单商品为空")
    return valid_items


def _parse_delivery(raw: str) -> dict:
    """解析订单配送 JSON，空值或非法结构直接报错。"""
    if not str(raw or "").strip():
        raise ValueError("订单配送 JSON 为空")
    try:
        delivery = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("订单配送 JSON 非法") from exc
    if not isinstance(delivery, dict):
        raise ValueError("订单配送 JSON 必须是对象")
    return delivery


def _parse_payment(raw: str) -> dict:
    """支付快照仅用于展示状态，解析失败按未支付处理。"""
    try:
        payment = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return payment if isinstance(payment, dict) else {}


def _format_fen(value: object) -> str:
    """把分格式化为两位小数元。"""
    try:
        amount_fen = max(int(value or 0), 0)
    except (TypeError, ValueError):
        amount_fen = 0
    return f"{amount_fen / 100:.2f}"


def _format_total(value: object) -> str:
    """把订单元金额格式化为两位小数。"""
    try:
        return f"{float(value or 0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _fulfillment_label(delivery: dict) -> str:
    """履约方式中文化，未知值原样展示。"""
    method = str(
        delivery.get("fulfillmentMethod") or delivery.get("deliveryType") or ""
    ).strip()
    return FULFILLMENT_LABELS.get(method, method or "未填写")


def _payment_label(order: Order) -> str:
    """只展示支付状态，不展示储值流水。"""
    payment = _parse_payment(order.payment)
    status = str(payment.get("status", "unpaid")).strip()
    return PAYMENT_LABELS.get(status, status or "未支付")


def _is_cake_item(item: dict) -> bool:
    """按履约类型、定制信息或标题关键词判定蛋糕项。"""
    return (
        classify_fulfillment_type(item, str(item.get("title", "")))
        == FULFILLMENT_PREORDER_CAKE
    )


def _split_items(products: list[dict]) -> tuple[list[dict], list[dict]]:
    """拆分蛋糕项与日常项；显式日常项不会因标题关键词误入蛋糕联。"""
    cake_items: list[dict] = []
    daily_items: list[dict] = []
    for item in products:
        if _is_cake_item(item):
            cake_items.append(item)
        else:
            daily_items.append(item)
    return cake_items, daily_items


def _render_header(
    lines: list[str],
    title: str,
    order: Order,
    delivery: dict,
    width: int,
) -> None:
    """写入两张小票共用的头部信息。"""
    _append_line(lines, title, width)
    _append_kv(lines, "订单号", order.id, width)
    _append_kv(lines, "履约方式", _fulfillment_label(delivery), width)
    _append_kv(lines, "预约时段", delivery.get("expectTime", ""), width)
    _append_kv(lines, "客户姓名", delivery.get("receiverName", ""), width)
    _append_kv(lines, "联系电话", delivery.get("receiverPhone", ""), width)


def _render_cake_ticket(
    order: Order, delivery: dict, items: list[dict], width: int
) -> str:
    """生成裱花间制作联，不包含任何储值余额信息。"""
    lines: list[str] = []
    _render_header(lines, CAKE_TICKET_TITLE, order, delivery, width)
    _append_line(lines, "-" * width, width)
    _append_line(lines, "蛋糕制作明细", width)
    for index, item in enumerate(items, 1):
        title = str(item.get("title") or "定制蛋糕").strip()
        quantity = int(item.get("quantity") or 0)
        _append_line(lines, f"{index}. {title} x{quantity}", width)
        customization = item.get("customization")
        if not isinstance(customization, dict):
            customization = {}
        _append_kv(lines, "尺寸", customization.get("size", ""), width)
        _append_kv(lines, "夹心", customization.get("filling", ""), width)
        _append_kv(lines, "祝福语", customization.get("greeting", ""), width)
        accessories = str(customization.get("accessories", "")).strip()
        if not accessories:
            accessories = " ".join(
                str(value).strip()
                for value in (
                    customization.get("tableware"),
                    customization.get("candle"),
                )
                if str(value or "").strip()
            )
        _append_kv(lines, "配件", accessories, width)
        _append_kv(lines, "备注", item.get("remark", ""), width)
    _append_line(lines, "-" * width, width)
    _append_kv(lines, "订单备注", order.remark, width)
    _append_kv(lines, "下单时间", order.created_at, width)
    return "\n".join(lines)


def _render_daily_ticket(
    order: Order,
    delivery: dict,
    items: list[dict],
    width: int,
) -> str:
    """生成日常现烤/配送联，包含商品、金额与配送信息。"""
    lines: list[str] = []
    _render_header(lines, DAILY_TICKET_TITLE, order, delivery, width)
    method = str(
        delivery.get("fulfillmentMethod") or delivery.get("deliveryType") or ""
    ).strip()
    if method in ("beijing_delivery", "delivery"):
        _append_kv(lines, "配送地址", delivery.get("deliveryAddress", ""), width)
    else:
        _append_kv(lines, "自提地址", delivery.get("pickupAddress", ""), width)
    _append_line(lines, "-" * width, width)
    _append_line(lines, "商品明细", width)
    for index, item in enumerate(items, 1):
        title = str(item.get("title") or "商品").strip()
        quantity = int(item.get("quantity") or 0)
        amount = _format_fen(item.get("price_fen"))
        _append_line(lines, f"{index}. {title} x{quantity}  {amount}", width)
    _append_line(lines, "-" * width, width)
    _append_kv(lines, "订单金额", f"￥{_format_total(order.total_amount)}", width)
    _append_kv(lines, "支付状态", _payment_label(order), width)
    _append_kv(lines, "订单备注", order.remark, width)
    _append_kv(lines, "下单时间", order.created_at, width)
    return "\n".join(lines)


def build_print_tickets(
    order: Order,
    *,
    width: int = DEFAULT_TICKET_WIDTH,
) -> list[PrintTicket]:
    """按订单内容生成需要打印的小票，打印路由留给 3B。"""
    products = _parse_products(order.products)
    delivery = _parse_delivery(order.delivery)
    cake_items, daily_items = _split_items(products)
    tickets: list[PrintTicket] = []
    if cake_items:
        tickets.append(
            PrintTicket(
                ticket_type=PrintTicketType.CAKE_KITCHEN.value,
                content=_render_cake_ticket(order, delivery, cake_items, width),
                printer_id="",
            )
        )
    if daily_items:
        tickets.append(
            PrintTicket(
                ticket_type=PrintTicketType.DAILY_FRONT.value,
                content=_render_daily_ticket(order, delivery, daily_items, width),
                printer_id="",
            )
        )
    return tickets


__all__ = [
    "CAKE_TICKET_TITLE",
    "DAILY_TICKET_TITLE",
    "DEFAULT_TICKET_WIDTH",
    "FULFILLMENT_LABELS",
    "build_print_tickets",
    "wrap_display_width",
]
