"""订单库存协作逻辑。"""

from dataclasses import dataclass, field

from app.models.order import Order
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.catalog.daily_stock import ProductDailyStockService
from app.service.catalog.product_options import (
    ORDER_MODE_PREORDER,
    SIZE_PROPERTY_NAME,
    build_product_options,
)
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
    sku_id: str = ""
    customization: dict = field(default_factory=dict)
    line_key: str = ""


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
        """将前端商品项合并为后端订单商品项。

        同一商品的不同规格/选项必须保留为独立行，合并键包含 SKU 与选项；
        价格一律由服务端按「SKU 价 + 选项加价」重算，不信任前端报价。
        """
        if not isinstance(raw_items, list):
            return []
        lines = self._build_item_lines(raw_items)
        if not lines:
            return []
        product_ids = sorted({line["product_id"] for line in lines})
        stock_map = await self._product_repo.get_prices_and_stocks(product_ids)
        option_rows = await self._product_repo.get_option_rows(product_ids)
        items: list[NormalizedOrderItem] = []
        for line in lines:
            product_id = line["product_id"]
            stock_item = stock_map.get(product_id, {})
            row = option_rows.get(product_id) or {}
            catalog_title = str(stock_item.get("title") or line["title"])
            options_model = build_product_options(
                str(row.get("skus_json") or ""),
                str(row.get("item_props_json") or ""),
                base_price_fen=int(row.get("price_fen") or 0),
            )
            selection = self._resolve_selection(line, options_model, catalog_title)
            fulfillment_type = self._resolve_fulfillment_type(
                line, options_model, catalog_title
            )
            self._validate_sellable_stock(
                product_id,
                line,
                stock_item,
                check_stock=not (
                    fulfillment_type == FULFILLMENT_DAILY_READY
                    and self._daily_stock_service is not None
                ),
            )
            if fulfillment_type == FULFILLMENT_PREORDER_CAKE:
                self._validate_variant_stock(product_id, selection)
            items.append(
                NormalizedOrderItem(
                    product_id=product_id,
                    title=self._build_line_title(catalog_title, selection),
                    price_fen=self._resolve_line_price(stock_item, line, selection),
                    quantity=line["quantity"],
                    uses_catalog_inventory=bool(stock_item),
                    fulfillment_type=fulfillment_type,
                    sku_id=selection["sku_id"],
                    customization=(
                        self._build_customization(line, selection)
                        if fulfillment_type == FULFILLMENT_PREORDER_CAKE
                        else {}
                    ),
                    line_key=line["line_key"],
                )
            )
        return items

    @staticmethod
    def _resolve_fulfillment_type(
        line: dict, options_model: dict, catalog_title: str = ""
    ) -> str:
        """履约类型判定优先级：显式声明 > 商品有规格/属性 > 标题关键词 > 日常现烤。

        有尺寸或定制属性的商品必须提前预订；标题命中定制关键词的历史商品
        也按预订处理，保证旧数据与旧客户端行为不变。
        """
        explicit = str(line.get("fulfillment_type") or "").strip().upper()
        if explicit in (FULFILLMENT_PREORDER_CAKE, FULFILLMENT_DAILY_READY):
            return explicit
        # 客户端提交了定制信息，等价于声明这是定制蛋糕
        if isinstance(line.get("customization"), dict) and line["customization"]:
            return FULFILLMENT_PREORDER_CAKE
        if options_model["orderMode"] == ORDER_MODE_PREORDER:
            return FULFILLMENT_PREORDER_CAKE
        title = str(line.get("title") or catalog_title or "")
        if (
            classify_fulfillment_type({"title": title}, title)
            == FULFILLMENT_PREORDER_CAKE
        ):
            return FULFILLMENT_PREORDER_CAKE
        return FULFILLMENT_DAILY_READY

    @staticmethod
    def _build_customization(line: dict, selection: dict) -> dict:
        """组装定制信息：客户端显式提交的定制必须完整，否则用规格/选项补默认值。

        - 显式提交 customization：原样交给双轨校验，缺项（如夹心）直接报错；
        - 未提交 customization 但选了规格/选项：用选择结果补默认值；
        - 两者都没有：返回空字典，由双轨校验报“必须提供定制信息”。
        """
        raw = line.get("customization")
        explicit = (
            {
                key: str(raw.get(key) or "").strip()
                for key in ("size", "filling", "sweetness", "greeting", "accessories")
                if str(raw.get(key) or "").strip()
            }
            if isinstance(raw, dict)
            else {}
        )
        if explicit:
            return explicit
        has_selection = selection["variant"] is not None or bool(selection["choices"])
        if not has_selection:
            return {}
        return dict(selection["customization"])

    def _build_item_lines(self, raw_items: list) -> list[dict]:
        """按「商品 + 规格 + 选项 + 定制文字」拆行，避免不同定制被合并成一行。"""
        lines: dict[str, dict] = {}
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            product_id = str(raw_item.get("productId", "")).strip()
            quantity = self._to_non_negative_int(raw_item.get("quantity"))
            if not product_id or quantity == 0:
                continue
            sku_id = str(raw_item.get("skuId") or "").strip()
            choice_ids = sorted(
                str(choice).strip()
                for choice in (raw_item.get("optionChoiceIds") or [])
                if str(choice).strip()
            )
            greeting = str(raw_item.get("greeting") or "").strip()
            accessories = str(raw_item.get("accessories") or "").strip()
            fulfillment_type = (
                str(
                    raw_item.get("fulfillmentType")
                    or raw_item.get("fulfillment_type")
                    or ""
                )
                .strip()
                .upper()
            )
            raw_customization = raw_item.get("customization")
            line_key = "|".join(
                [product_id, sku_id, ",".join(choice_ids), greeting, accessories]
            )
            current = lines.get(line_key)
            if current is None:
                lines[line_key] = {
                    "line_key": line_key,
                    "product_id": product_id,
                    "title": str(raw_item.get("title") or ""),
                    "price_fen": self._to_non_negative_int(raw_item.get("priceFen")),
                    "quantity": quantity,
                    "sku_id": sku_id,
                    "option_choice_ids": choice_ids,
                    "greeting": greeting,
                    "accessories": accessories,
                    "fulfillment_type": fulfillment_type,
                    "customization": (
                        raw_customization if isinstance(raw_customization, dict) else {}
                    ),
                }
                continue
            current["quantity"] += quantity
        return list(lines.values())

    def _resolve_selection(
        self,
        line: dict,
        options_model: dict,
        title: str,
    ) -> dict:
        """校验规格与选项，并组装订单定制信息。"""
        variants = options_model["variants"]
        option_groups = options_model["options"]
        variant = None
        if variants:
            requested_sku = line["sku_id"]
            if not requested_sku:
                if len(variants) > 1:
                    raise ValueError(f"请选择规格: {title}")
                variant = variants[0]
            else:
                variant = next(
                    (item for item in variants if item["id"] == requested_sku), None
                )
                if variant is None:
                    raise ValueError("所选规格已失效，请重新选择")
        selected_ids = set(line["option_choice_ids"])
        known_ids = {
            choice["id"] for group in option_groups for choice in group["choices"]
        }
        if selected_ids - known_ids:
            raise ValueError("所选选项已失效，请重新选择")
        chosen: list[tuple[str, dict]] = []
        for group in option_groups:
            group_choices = [
                choice for choice in group["choices"] if choice["id"] in selected_ids
            ]
            if group["required"] and not group_choices:
                raise ValueError(f"请选择{group['name']}")
            if not group["multiple"] and len(group_choices) > 1:
                raise ValueError(f"{group['name']}只能选一项")
            chosen.extend((group["name"], choice) for choice in group_choices)
        size = (
            variant["name"]
            if variant is not None and variant["property"] == SIZE_PROPERTY_NAME
            else ""
        )
        customization = {
            "size": size or "标准",
            "filling": self._join_choice_names(chosen, "夹心") or "标准",
            "sweetness": self._join_choice_names(chosen, "甜度"),
            "greeting": line["greeting"] or "无",
            "accessories": line["accessories"] or "无",
            "options": [
                {
                    "group": group_name,
                    "name": choice["name"],
                    "priceDeltaFen": choice["priceDeltaFen"],
                }
                for group_name, choice in chosen
            ],
        }
        return {
            "sku_id": str(variant["id"]) if variant is not None else "",
            "variant": variant,
            "choices": [choice for _, choice in chosen],
            "size": size,
            "option_summary": "、".join(choice["name"] for _, choice in chosen),
            "customization": customization,
        }

    @staticmethod
    def _join_choice_names(chosen: list[tuple[str, dict]], group_name: str) -> str:
        """把同一属性组选中的选项名拼成一段可读文本。"""
        return "、".join(
            choice["name"] for name, choice in chosen if name == group_name
        )

    def _resolve_line_price(
        self,
        stock_item: dict,
        line: dict,
        selection: dict,
    ) -> int:
        """单价 = SKU 价（无 SKU 时取商品价）+ 选项加价。"""
        variant = selection["variant"]
        base_price = (
            int(variant["priceFen"])
            if variant is not None
            else int(stock_item.get("price_fen") or line.get("price_fen") or 0)
        )
        delta = sum(int(choice["priceDeltaFen"]) for choice in selection["choices"])
        price_fen = base_price + delta
        if price_fen <= 0:
            raise ValueError(f"商品价格无效: {line['product_id']}")
        return price_fen

    @staticmethod
    def _validate_variant_stock(product_id: str, selection: dict) -> None:
        """预订商品按 SKU 库存校验，没有 SKU 的按有赞商品库存放行。"""
        variant = selection["variant"]
        if variant is not None and int(variant.get("stock") or 0) <= 0:
            raise ValueError(f"该规格已售罄: {variant['name']}")

    @staticmethod
    def _build_line_title(title: str, selection: dict) -> str:
        """订单行标题带上规格与选项，便于小票与客服核对。"""
        extras = [
            value for value in (selection["size"], selection["option_summary"]) if value
        ]
        return f"{title}（{'/'.join(extras)}）" if extras else title

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
