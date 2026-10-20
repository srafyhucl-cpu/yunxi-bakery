"""订单小票排版测试。"""

import json
import unicodedata

import pytest

from app.models.order import Order
from app.models.print_job import PrintTicketType
from app.service.order.print_jobs import build_print_tickets, wrap_display_width

CAKE_ITEM = {
    "product_id": 101,
    "title": "草莓定制蛋糕",
    "price_fen": 19800,
    "quantity": 1,
    "fulfillment_type": "PREORDER_CAKE",
    "customization": {
        "size": "8寸",
        "filling": "草莓奶油夹心",
        "greeting": "生日快乐",
        "accessories": "餐具+数字蜡烛",
    },
}
DAILY_ITEM = {
    "product_id": 201,
    "title": "现烤黄油可颂",
    "price_fen": 1500,
    "quantity": 2,
    "fulfillment_type": "DAILY_READY",
}
DELIVERY = {
    "receiverName": "张三",
    "receiverPhone": "13800000000",
    "fulfillmentMethod": "pickup",
    "pickupAddress": "芸熙烘焙门店",
    "expectTime": "2026-10-20 15:00",
}
PAYMENT = {"status": "paid", "balanceFen": 18800, "method": "wechat"}


def _order(products: list[dict], delivery: dict | None = None) -> Order:
    return Order(
        id="order_print_001",
        session_id="session_001",
        channel="storefront",
        user_id="user_001",
        products=json.dumps(products, ensure_ascii=False),
        total_amount=198.0,
        delivery=json.dumps(delivery or DELIVERY, ensure_ascii=False),
        payment=json.dumps(PAYMENT, ensure_ascii=False),
        remark="请提前十分钟电话联系",
        created_at="2026-10-19 10:00:00",
        updated_at="2026-10-19 10:00:00",
    )


def _display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def test_cake_order_only_builds_kitchen_ticket_without_balance() -> None:
    """蛋糕订单只出制作联，包含定制信息且不打印储值余额。"""
    tickets = build_print_tickets(_order([CAKE_ITEM]))

    assert [ticket.ticket_type for ticket in tickets] == [
        PrintTicketType.CAKE_KITCHEN.value
    ]
    content = tickets[0].content
    assert "【裱花间制作联】" in content
    for expected in ("8寸", "草莓奶油夹心", "生日快乐", "餐具+数字蜡烛", "到店自提"):
        assert expected in content
    assert "储值" not in content
    assert "188.00" not in content


def test_daily_order_only_builds_front_ticket_with_amount_and_delivery() -> None:
    """日常订单只出配送联，包含商品、金额、履约与配送信息。"""
    delivery = {
        **DELIVERY,
        "fulfillmentMethod": "beijing_delivery",
        "deliveryAddress": "北京市朝阳区幸福路 1 号",
    }
    order = _order([DAILY_ITEM], delivery)
    order.total_amount = 30.0

    tickets = build_print_tickets(order)

    assert [ticket.ticket_type for ticket in tickets] == [
        PrintTicketType.DAILY_FRONT.value
    ]
    content = tickets[0].content
    normalized = content.replace("\n", "")
    assert "【日常现烤/配送联】" in normalized
    for expected in (
        "现烤黄油可颂",
        "x2",
        "30.00",
        "同城闪送",
        "北京市朝阳区幸福路 1 号",
        "已支付",
    ):
        assert expected in normalized


def test_mixed_order_builds_two_tickets() -> None:
    """蛋糕与日常商品同时存在时必须出两张联单。"""
    tickets = build_print_tickets(_order([CAKE_ITEM, DAILY_ITEM]))

    assert {ticket.ticket_type for ticket in tickets} == {
        PrintTicketType.CAKE_KITCHEN.value,
        PrintTicketType.DAILY_FRONT.value,
    }
    kitchen = next(
        ticket
        for ticket in tickets
        if ticket.ticket_type == PrintTicketType.CAKE_KITCHEN.value
    )
    assert "现烤黄油可颂" not in kitchen.content


def test_wrap_display_width_keeps_each_line_within_limit() -> None:
    """中文按 2 宽度换行，每行不超过 32 且不丢字符。"""
    text = "生日蛋糕请使用动物奶油并在上午十点前完成裱花，祝福牌写生日快乐"

    lines = wrap_display_width(text, 32)

    assert all(_display_width(line) <= 32 for line in lines)
    assert "".join(lines) == text


def test_invalid_products_json_raises_value_error() -> None:
    """空或非法商品 JSON 直接报错，不生成空联单。"""
    order = _order([CAKE_ITEM])
    order.products = "{invalid"

    with pytest.raises(ValueError, match="商品 JSON"):
        build_print_tickets(order)
