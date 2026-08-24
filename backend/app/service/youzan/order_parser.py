"""有赞订单 API 响应解析器。

提取 event_trade / function_tool_order 两处完全相同的 full_order_info 解析逻辑，
统一封装为 ParsedOrderData + parse_youzan_order_response。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParsedOrderData:
    """从有赞 trade.get API 响应中提取的订单核心字段。"""

    foi: dict
    order_info: dict
    pay_info: dict
    addr_info: dict
    status: str
    payment_fen: int
    post_fee: float
    post_fee_fen: int
    discount_fen: int
    buyer_id: str
    outer_user_id: str
    order_items: list
    items_detail: list = field(default_factory=list)
    product_titles: str = ""
    total_qty: int = 0


def parse_youzan_order_response(raw_order: dict) -> ParsedOrderData | None:
    """解析有赞 trade.get API 响应，提取订单核心字段。

    返回：
        ParsedOrderData — 解析成功
        None — 响应结构异常，缺少 full_order_info
    """
    outer_data = raw_order.get("data") if isinstance(raw_order, dict) else None
    if not isinstance(outer_data, dict) or "full_order_info" not in outer_data:
        return None

    foi = outer_data["full_order_info"]
    order_info = foi.get("order_info", {})
    pay_info = foi.get("pay_info", {})
    buyer_info = foi.get("buyer_info", {})
    addr_info = foi.get("address_info", {})

    status = order_info.get("status", "WAIT_BUYER_PAY")
    payment_fen = int(float(pay_info.get("payment", 0)) * 100)
    total_fee = float(pay_info.get("total_fee", 0))
    post_fee = float(pay_info.get("post_fee", 0))
    post_fee_fen = int(post_fee * 100)
    discount_fen = max(
        0, int((total_fee + post_fee - float(pay_info.get("payment", 0))) * 100)
    )
    buyer_id = str(buyer_info.get("buyer_id", "") or buyer_info.get("open_id", ""))
    outer_user_id = str(buyer_info.get("outer_user_id", ""))

    order_items = foi.get("orders", [])
    titles_list: list[str] = []
    total_qty = 0
    items_detail: list[dict] = []
    for item in order_items:
        title = item.get("title", item.get("goods_title", "商品"))
        num = item.get("num", 1)
        titles_list.append(f"{title} x {num}")
        total_qty += num
        items_detail.append(
            {
                "oid": item.get("oid", ""),
                "item_id": item.get("item_id", 0),
                "alias": item.get("alias", ""),
                "title": title,
                "num": num,
                "price": item.get("price", "0"),
                "sku_properties_name": item.get("sku_properties_name", ""),
                "buyer_messages": item.get("buyer_messages", ""),
            }
        )

    return ParsedOrderData(
        foi=foi,
        order_info=order_info,
        pay_info=pay_info,
        addr_info=addr_info,
        status=status,
        payment_fen=payment_fen,
        post_fee=post_fee,
        post_fee_fen=post_fee_fen,
        discount_fen=discount_fen,
        buyer_id=buyer_id,
        outer_user_id=outer_user_id,
        order_items=order_items,
        items_detail=items_detail,
        product_titles=", ".join(titles_list),
        total_qty=total_qty,
    )
