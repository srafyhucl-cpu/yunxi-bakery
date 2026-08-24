"""企微智能机器人工具商品动作建议。"""

from __future__ import annotations

from typing import Any

NO_STOCK_VALUE = 0
LOW_STOCK_THRESHOLD = 5


def product_next_action(query: str, products: list[dict[str, Any]]) -> str:
    """按命中商品库存生成员工下一步动作。"""
    if not products:
        return "请换商品名、品类或关键词再查；不要把未命中结果当作缺货结论。"
    stock_values = [int(product.get("stock", 0) or 0) for product in products]
    if max(stock_values) <= NO_STOCK_VALUE:
        return (
            "当前命中商品暂无可售库存，先不要承诺有货；可推荐同品类或相近价位替代款。"
        )
    if min(stock_values) <= LOW_STOCK_THRESHOLD:
        return "当前命中商品存在低库存，先确认客户数量、规格和配送/自提时间，避免超卖。"
    if _asks_enough_stock(query):
        return "当前命中商品库存充足；如客户要量较大，再到后台或小程序核对实时库存。"
    return "库存和价格以小程序商品数据为准；可按当前库存回复，特殊数量先人工核对。"


def _asks_enough_stock(query: str) -> bool:
    return any(word in query for word in ("够吗", "还够", "够不够", "库存不够"))
