"""订单库存协作逻辑。"""

from dataclasses import dataclass

from app.models.order import Order
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo


@dataclass
class NormalizedOrderItem:
    """订单商品项。"""

    product_id: str
    title: str
    price_fen: int
    quantity: int
    uses_catalog_inventory: bool = False
    inventory_reserved: bool = False


class OrderInventoryService:
    """负责订单商品标准化、真实库存校验、预占和释放。"""

    def __init__(
        self,
        product_repo: YouzanProductRepo,
        inventory_repo: YouzanInventoryRepo,
    ) -> None:
        self._product_repo = product_repo
        self._inventory_repo = inventory_repo

    async def normalize_items(self, raw_items: object) -> list[NormalizedOrderItem]:
        """将前端商品项合并为后端订单商品项。"""
        if not isinstance(raw_items, list):
            return []
        fallback_by_id = self._build_fallback_item_map(raw_items)
        stock_map = await self._product_repo.get_prices_and_stocks(
            list(fallback_by_id.keys())
        )
        items: list[NormalizedOrderItem] = []
        for product_id, fallback in fallback_by_id.items():
            stock_item = stock_map.get(product_id, {})
            self._validate_sellable_stock(product_id, fallback, stock_item)
            items.append(
                NormalizedOrderItem(
                    product_id=product_id,
                    title=fallback["title"],
                    price_fen=int(stock_item.get("price_fen") or fallback["price_fen"]),
                    quantity=fallback["quantity"],
                    uses_catalog_inventory=bool(stock_item),
                )
            )
        return items

    async def reserve_inventory(self, order_items: list[NormalizedOrderItem]) -> None:
        """预占真实商品库存，失败时回滚本次已预占项。"""
        reserved_items: list[NormalizedOrderItem] = []
        for item in order_items:
            if not item.uses_catalog_inventory:
                continue
            is_reserved = await self._inventory_repo.reserve_stock(
                item.product_id,
                item.quantity,
            )
            if not is_reserved:
                await self.release_reserved_inventory(reserved_items)
                raise ValueError(f"商品库存不足: {item.product_id}")
            item.inventory_reserved = True
            reserved_items.append(item)

    async def release_reserved_inventory(
        self, order_items: list[NormalizedOrderItem]
    ) -> None:
        """释放订单中已预占的真实商品库存。"""
        for item in order_items:
            if item.inventory_reserved:
                await self._inventory_repo.release_stock(item.product_id, item.quantity)

    def items_from_order(self, order: Order) -> list[NormalizedOrderItem]:
        """从订单 JSON 中恢复库存释放所需商品项。"""
        items: list[NormalizedOrderItem] = []
        for raw_item in self._loads_list(order.products):
            if not isinstance(raw_item, dict):
                continue
            items.append(
                NormalizedOrderItem(
                    product_id=str(raw_item.get("product_id", "")),
                    title=str(raw_item.get("title", "")),
                    price_fen=self._to_non_negative_int(raw_item.get("price_fen")),
                    quantity=self._to_non_negative_int(raw_item.get("quantity")),
                    inventory_reserved=bool(raw_item.get("inventory_reserved")),
                )
            )
        return items

    def _validate_sellable_stock(
        self,
        product_id: str,
        fallback: dict,
        stock_item: dict,
    ) -> None:
        if not stock_item:
            return
        if int(stock_item.get("is_active") or 0) != 1:
            raise ValueError(f"商品已下架: {product_id}")
        stock = self._to_non_negative_int(stock_item.get("stock"))
        quantity = self._to_non_negative_int(fallback.get("quantity"))
        if stock <= 0:
            raise ValueError(f"商品已售罄: {product_id}")
        if quantity > stock:
            raise ValueError(f"商品库存不足: {product_id}")
        price_fen = self._to_non_negative_int(stock_item.get("price_fen"))
        if price_fen <= 0 and self._to_non_negative_int(fallback.get("price_fen")) <= 0:
            raise ValueError(f"商品价格无效: {product_id}")

    def _build_fallback_item_map(self, raw_items: list) -> dict[str, dict]:
        fallback_by_id: dict[str, dict] = {}
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            product_id = str(raw_item.get("productId", "")).strip()
            quantity = self._to_non_negative_int(raw_item.get("quantity"))
            if not product_id or quantity == 0:
                continue
            current_item = fallback_by_id.get(product_id, {})
            fallback_by_id[product_id] = {
                "title": str(
                    raw_item.get("title") or current_item.get("title") or product_id
                ),
                "price_fen": self._to_non_negative_int(raw_item.get("priceFen"))
                or int(current_item.get("price_fen", 0)),
                "quantity": quantity + int(current_item.get("quantity", 0)),
            }
        return fallback_by_id

    def _to_non_negative_int(self, value: object) -> int:
        try:
            return max(int(value or 0), 0)
        except (TypeError, ValueError):
            return 0

    def _loads_list(self, raw: str) -> list[dict]:
        import json

        try:
            value = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return []
        return value if isinstance(value, list) else []


__all__ = ["NormalizedOrderItem", "OrderInventoryService"]
