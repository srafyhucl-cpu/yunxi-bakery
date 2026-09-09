"""配送平台内部适配协议。"""

import hashlib
import json
from dataclasses import dataclass
from collections.abc import Iterable
from typing import Protocol

from app.models.delivery import DeliveryOrder, DeliveryQuote


@dataclass(frozen=True)
class DeliveryQuoteItem:
    """配送报价绑定的商品与数量。"""

    product_id: str
    quantity: int


@dataclass(frozen=True)
class DeliveryQuoteRequest:
    """供应商无关的配送报价请求。"""

    request_id: str
    pickup_address: str
    receiver_name: str
    receiver_phone: str
    receiver_address: str
    expect_time: str
    item_count: int
    user_id: str = ""
    goods_total_fen: int = 0
    items: tuple[DeliveryQuoteItem, ...] = ()


class DeliveryProvider(Protocol):
    """配送平台适配器的最小协议。"""

    async def quote(self, request: DeliveryQuoteRequest) -> DeliveryQuote: ...

    async def create_order(
        self, request: DeliveryQuoteRequest, quote: DeliveryQuote
    ) -> DeliveryOrder: ...

    async def cancel_order(
        self, provider_order_id: str, reason: str
    ) -> DeliveryOrder: ...


def build_delivery_request_hash(request: DeliveryQuoteRequest) -> str:
    """为订单绑定字段生成不含客户原文的稳定摘要。"""
    payload = {
        "fulfillment_method": "beijing_delivery",
        "pickup_address": request.pickup_address.strip(),
        "receiver_name": request.receiver_name.strip(),
        "receiver_phone": request.receiver_phone.strip(),
        "receiver_address": request.receiver_address.strip(),
        "expect_time": request.expect_time.strip(),
        "item_count": request.item_count,
        "goods_total_fen": request.goods_total_fen,
        "items": [
            {"product_id": item.product_id, "quantity": item.quantity}
            for item in normalize_delivery_quote_items(request.items)
        ],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_delivery_quote_items(
    items: Iterable[DeliveryQuoteItem],
) -> tuple[DeliveryQuoteItem, ...]:
    """合并同商品项，形成用于报价绑定的稳定商品集合。"""
    quantities: dict[str, int] = {}
    for item in items:
        product_id = item.product_id.strip()
        if not product_id or item.quantity <= 0:
            raise ValueError("配送报价商品参数无效")
        quantities[product_id] = quantities.get(product_id, 0) + item.quantity
    if not quantities:
        raise ValueError("配送报价商品不能为空")
    return tuple(
        DeliveryQuoteItem(product_id=product_id, quantity=quantity)
        for product_id, quantity in sorted(quantities.items())
    )
