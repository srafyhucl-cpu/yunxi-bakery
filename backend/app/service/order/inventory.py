"""订单库存协作逻辑。"""

from dataclasses import dataclass

from app.models.order import Order
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.catalog.daily_stock import ProductDailyStockService
from app.service.catalog.purchasability import is_product_purchasable
from app.service.order.fulfillment_types import (
    FULFILLMENT_DAILY_READY,
    FULFILLMENT_PREORDER_CAKE,
    classify_fulfillment_type,
)


@dataclass
class NormalizedOrderItem:
    """订单商品项。"""

    product_id: str
    title: str
    price_fen: int
    quantity: int
    uses_catalog_inventory: bool = False
    inventory_reserved: bool = False
    fulfillment_type: str = ""
    stock_date: str = ""
    daily_stock_reserved: bool = False


class OrderInventoryService:
    """负责订单商品标准化、真实库存校验、预占和释放。"""

    def __init__(
        self,
        product_repo: YouzanProductRepo,
        inventory_repo: YouzanInventoryRepo,
        daily_stock_service: ProductDailyStockService | None = None,
    ) -> None:
        self._product_repo = product_repo
        self._inventory_repo = inventory_repo
        self._daily_stock_service = daily_stock_service

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
            catalog_title = str(stock_item.get("title") or fallback["title"])
            fulfillment_type = self._resolve_fulfillment_type(
                fallback.get("raw_items", []),
                catalog_title,
            )
            self._validate_sellable_stock(
                product_id,
                fallback,
                stock_item,
                check_stock=not (
                    fulfillment_type == FULFILLMENT_DAILY_READY
                    and self._daily_stock_service is not None
                ),
            )
            items.append(
                NormalizedOrderItem(
                    product_id=product_id,
                    title=catalog_title,
                    price_fen=int(stock_item.get("price_fen") or fallback["price_fen"]),
                    quantity=fallback["quantity"],
                    uses_catalog_inventory=bool(stock_item),
                    fulfillment_type=fulfillment_type,
                )
            )
        return items

    def _resolve_fulfillment_type(
        self,
        raw_items: list[dict],
        catalog_title: str,
    ) -> str:
        """同一商品重复出现时，只要任一项命中定制蛋糕就按定制蛋糕处理。"""
        for raw_item in raw_items:
            if (
                classify_fulfillment_type(raw_item, catalog_title)
                == FULFILLMENT_PREORDER_CAKE
            ):
                return FULFILLMENT_PREORDER_CAKE
        return FULFILLMENT_DAILY_READY

    async def reserve_inventory(
        self,
        order_items: list[NormalizedOrderItem],
        *,
        stock_date: str = "",
    ) -> None:
        """预占订单库存，失败时回滚本次已预占项。

        每日库存服务存在时，日常现烤必须使用每日库存：商品未配置每日库存
        直接报错，不回退有赞库存；仅当服务未注入时沿用原有有赞库存路径。
        定制蛋糕始终使用有赞库存。
        """
        reserved_items: list[NormalizedOrderItem] = []
        for item in order_items:
            if not item.uses_catalog_inventory:
                continue
            try:
                daily_reserved = await self._reserve_daily_stock(item, stock_date)
            except ValueError:
                await self.release_reserved_inventory(reserved_items)
                raise
            if daily_reserved:
                reserved_items.append(item)
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

    async def _reserve_daily_stock(
        self,
        item: NormalizedOrderItem,
        stock_date: str,
    ) -> bool:
        """预占每日库存；每日库存服务存在时不允许静默回退有赞库存。"""
        daily_service = self._daily_stock_service
        if daily_service is None or item.fulfillment_type != FULFILLMENT_DAILY_READY:
            return False
        resolved_date = stock_date or daily_service.current_stock_date()
        await daily_service.ensure_date(resolved_date)
        record = await daily_service.get_for_date(item.product_id, resolved_date)
        if record is None:
            raise ValueError("商品今日未配置每日库存，请先在后台录入")
        reserved = await daily_service.reserve(
            item.product_id,
            resolved_date,
            item.quantity,
        )
        if not reserved:
            raise ValueError(f"商品今日库存不足: {item.product_id}")
        item.stock_date = resolved_date
        item.daily_stock_reserved = True
        return True

    async def release_reserved_inventory(
        self, order_items: list[NormalizedOrderItem]
    ) -> None:
        """按预占来源释放每日库存或真实商品库存。"""
        for item in order_items:
            if item.daily_stock_reserved:
                if self._daily_stock_service is not None and item.stock_date:
                    await self._daily_stock_service.release(
                        item.product_id,
                        item.stock_date,
                        item.quantity,
                    )
                continue
            if item.inventory_reserved:
                await self._inventory_repo.release_stock(item.product_id, item.quantity)

    def items_from_order(self, order: Order) -> list[NormalizedOrderItem]:
        """从订单 JSON 中恢复库存释放所需商品项。

        旧订单没有每日库存字段，保持原有有赞库存释放行为。
        """
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
                    fulfillment_type=str(raw_item.get("fulfillment_type", "")),
                    stock_date=str(raw_item.get("stock_date", "")),
                    daily_stock_reserved=bool(raw_item.get("daily_stock_reserved")),
                )
            )
        return items

    def _validate_sellable_stock(
        self,
        product_id: str,
        fallback: dict,
        stock_item: dict,
        *,
        check_stock: bool = True,
    ) -> None:
        if not stock_item:
            raise ValueError(f"商品不存在: {product_id}")
        product_title = str(stock_item.get("title") or fallback.get("title") or "")
        if not is_product_purchasable(product_title):
            raise ValueError(f"商品仅供展示，不可下单: {product_id}")
        if int(stock_item.get("is_active") or 0) != 1:
            raise ValueError(f"商品已下架: {product_id}")
        if check_stock:
            stock = self._to_non_negative_int(stock_item.get("stock"))
            quantity = self._to_non_negative_int(fallback.get("quantity"))
            if stock <= 0:
                raise ValueError(f"商品已售罄: {product_id}")
            if quantity > stock:
                raise ValueError(f"商品库存不足: {product_id}")
        price_fen = self._to_non_negative_int(stock_item.get("price_fen"))
        if price_fen <= 0:
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
            merged_raw_items = [*current_item.get("raw_items", []), raw_item]
            fallback_by_id[product_id] = {
                "title": str(
                    raw_item.get("title") or current_item.get("title") or product_id
                ),
                "price_fen": self._to_non_negative_int(raw_item.get("priceFen"))
                or int(current_item.get("price_fen", 0)),
                "quantity": quantity + int(current_item.get("quantity", 0)),
                "raw_items": merged_raw_items,
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
