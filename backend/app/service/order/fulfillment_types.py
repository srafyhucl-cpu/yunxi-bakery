"""订单履约类型判定（定制蛋糕预订 / 日常现烤现货）。"""

FULFILLMENT_PREORDER_CAKE = "PREORDER_CAKE"
FULFILLMENT_DAILY_READY = "DAILY_READY"

CAKE_KEYWORDS = (
    "定制蛋糕",
    "预订蛋糕",
    "生日定制",
    "预订大蛋糕",
    "定制慕斯",
    "生巧慕斯定制",
)


def classify_fulfillment_type(raw_item: dict, title: str = "") -> str:
    """根据商品参数或标题判定履约类型。

    显式 fulfillment_type 优先；带 customization 或命中蛋糕关键词的视为定制蛋糕，
    其余默认按日常现烤现货处理。
    """
    explicit = (
        str(raw_item.get("fulfillment_type") or raw_item.get("fulfillmentType") or "")
        .strip()
        .upper()
    )
    if explicit in (FULFILLMENT_PREORDER_CAKE, FULFILLMENT_DAILY_READY):
        return explicit
    if raw_item.get("customization"):
        return FULFILLMENT_PREORDER_CAKE
    item_title = str(raw_item.get("title") or title or "")
    if any(keyword in item_title for keyword in CAKE_KEYWORDS):
        return FULFILLMENT_PREORDER_CAKE
    return FULFILLMENT_DAILY_READY


__all__ = [
    "FULFILLMENT_PREORDER_CAKE",
    "FULFILLMENT_DAILY_READY",
    "CAKE_KEYWORDS",
    "classify_fulfillment_type",
]
