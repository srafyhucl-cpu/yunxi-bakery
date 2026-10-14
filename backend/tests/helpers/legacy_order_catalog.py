"""订单测试使用的历史合成商品夹具。"""

from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo


class LegacyOrderProductRepo(YouzanProductRepo):
    """为非目录型历史测试商品提供明确的测试目录数据。"""

    legacy_prices = {
        "p_m2_001": 5_000,
        "p_m3_api_001": 10_000,
        "p_m3_pay_001": 10_000,
        "p_m4_coupon_001": 10_000,
    }

    async def get_prices_and_stocks(self, item_ids: list[str]) -> dict[str, dict]:
        result = await super().get_prices_and_stocks(item_ids)
        for item_id in item_ids:
            if not item_id.isdigit():
                result[item_id] = {
                    "title": "历史合成测试商品",
                    "price_fen": self.legacy_prices.get(item_id, 19_800),
                    "stock": 999,
                    "is_active": 1,
                    "sold_num": 0,
                    "item_no": "",
                }
        return result


class LegacyOrderInventoryRepo(YouzanInventoryRepo):
    """为历史合成测试商品提供不触碰真实目录的库存桩。"""

    async def reserve_stock(self, item_id: str, quantity: int) -> bool:
        if not item_id.isdigit():
            return True
        return await super().reserve_stock(item_id, quantity)

    async def release_stock(self, item_id: str, quantity: int) -> bool:
        if not item_id.isdigit():
            return True
        return await super().release_stock(item_id, quantity)
