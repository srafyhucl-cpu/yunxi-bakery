"""商品可购买性策略。

有赞后台保留了少量用于原料说明或品牌展示的条目，这些条目标题会明确写有
“非卖品”“虚拟价格勿拍”等标记。它们需要继续出现在商品目录中供顾客了解，
但不能进入购物车或创建订单。
"""

DISPLAY_ONLY_TITLE_MARKERS = (
    "非卖品",
    "勿拍",
    "虚拟价格",
    "仅供展示",
)


def is_product_purchasable(title: str) -> bool:
    """判断商品标题是否允许直接下单。"""

    normalized = "".join((title or "").split())
    if not normalized:
        return True
    return not any(marker in normalized for marker in DISPLAY_ONLY_TITLE_MARKERS)


__all__ = ["DISPLAY_ONLY_TITLE_MARKERS", "is_product_purchasable"]
