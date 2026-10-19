"""定制蛋糕预订（PREORDER_CAKE）与日常现烤现货（DAILY_READY）双轨履约校验服务。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from app.logger import setup_logger
from app.models.order import OrderStatus
from app.repository.order_repo import OrderRepo
from app.service.order.cake_slots import (
    DEFAULT_CAKE_SLOT_CAPACITY,
    extract_slot_key as resolve_cake_slot_key,
)
from app.service.order.fulfillment_types import (
    CAKE_KEYWORDS,
    FULFILLMENT_DAILY_READY,
    FULFILLMENT_PREORDER_CAKE,
    classify_fulfillment_type,
)
from app.service.order.inventory import NormalizedOrderItem

logger = setup_logger()

BEIJING_TIME_ZONE = ZoneInfo("Asia/Shanghai")
EXPECT_TIME_FORMAT = "%Y-%m-%d %H:%M"

DEFAULT_CAKE_MIN_ADVANCE_HOURS = 4
DEFAULT_SLOT_MAX_CAPACITY = DEFAULT_CAKE_SLOT_CAPACITY


def get_current_beijing_time() -> datetime:
    """获取当前北京时间。"""
    return datetime.now(BEIJING_TIME_ZONE)


class OrderFulfillmentDualTrackService:
    """负责定制蛋糕与现烤现货双轨履约规则的严格校验。"""

    def __init__(
        self,
        order_repo: OrderRepo | None = None,
        now_provider: Callable[[], datetime] | None = None,
        slot_max_capacity: int = DEFAULT_SLOT_MAX_CAPACITY,
    ) -> None:
        self._order_repo = order_repo
        self._now_provider = now_provider or get_current_beijing_time
        self._slot_max_capacity = slot_max_capacity

    @staticmethod
    def classify_fulfillment_type(raw_item: dict, title: str = "") -> str:
        """根据商品参数或标题判定履约类型。"""
        return classify_fulfillment_type(raw_item, title)

    async def validate_fulfillment(
        self,
        *,
        items: list[dict],
        normalized_items: list[NormalizedOrderItem],
        delivery: dict,
        expect_time: str,
        check_capacity: bool = True,
    ) -> None:
        """执行双轨履约校验；check_capacity 为 False 时由原子预占服务接管容量。"""
        has_cake = False
        cake_min_advance_hours = DEFAULT_CAKE_MIN_ADVANCE_HOURS

        item_map = {
            str(item.get("product_id") or item.get("productId")): item for item in items
        }

        for norm_item in normalized_items:
            raw_item = item_map.get(str(norm_item.product_id), {})
            fulfillment_type = self.classify_fulfillment_type(raw_item, norm_item.title)
            if fulfillment_type == FULFILLMENT_PREORDER_CAKE:
                has_cake = True
                self.validate_cake_customization(raw_item, norm_item.title)
                item_advance = raw_item.get("min_advance_hours") or raw_item.get(
                    "minAdvanceHours"
                )
                if item_advance is not None:
                    try:
                        cake_min_advance_hours = max(
                            cake_min_advance_hours, int(item_advance)
                        )
                    except (ValueError, TypeError):
                        pass

        if has_cake:
            self.validate_advance_hours(
                expect_time, min_advance_hours=cake_min_advance_hours
            )
            if check_capacity and self._order_repo is not None:
                await self.validate_delivery_slot_capacity(expect_time)

    def validate_cake_customization(self, raw_item: dict, item_title: str) -> None:
        """强制校验定制蛋糕结构化信息（尺寸规格、夹心口味、写字祝福牌备注、餐具/蜡烛配件）。"""
        customization = raw_item.get("customization")
        if not isinstance(customization, dict):
            raise ValueError(
                f"定制蛋糕【{item_title}】必须提供定制信息（customization）"
            )

        size = str(customization.get("size", "")).strip()
        if not size:
            raise ValueError(f"定制蛋糕【{item_title}】必须指定尺寸规格（如6寸/8寸）")

        filling = str(customization.get("filling", "")).strip()
        if not filling:
            raise ValueError(f"定制蛋糕【{item_title}】必须选择夹心口味")

        greeting = str(customization.get("greeting", "")).strip()
        if not greeting:
            raise ValueError(f"定制蛋糕【{item_title}】缺少祝福牌备注（若无请填“无”）")

        accessories = str(customization.get("accessories", "")).strip()
        if not accessories:
            tableware = customization.get("tableware")
            candle = customization.get("candle")
            if not tableware and not candle:
                raise ValueError(f"定制蛋糕【{item_title}】缺少餐具/蜡烛配件信息")

    def validate_advance_hours(
        self,
        expect_time: str,
        min_advance_hours: int = DEFAULT_CAKE_MIN_ADVANCE_HOURS,
    ) -> None:
        """校验预约配送/自提时间满足定制蛋糕的最小提前预约小时数。"""
        if not expect_time:
            raise ValueError("预约时间不能为空")
        try:
            expect_dt = datetime.strptime(expect_time, EXPECT_TIME_FORMAT).replace(
                tzinfo=BEIJING_TIME_ZONE
            )
        except ValueError as exc:
            raise ValueError(f"预约时间格式无效: {expect_time}") from exc

        current_time = self._now_provider()
        delta_seconds = (expect_dt - current_time).total_seconds()
        min_required_seconds = min_advance_hours * 3600
        if delta_seconds < min_required_seconds:
            raise ValueError(f"定制蛋糕需至少提前 {min_advance_hours} 小时预约")

    async def validate_delivery_slot_capacity(self, expect_time: str) -> None:
        """校验预约配送/自提时段接单容量上限，防单时段爆单。"""
        if not expect_time or self._order_repo is None:
            return
        slot_key = self.extract_slot_key(expect_time)
        active_cake_orders = await self._count_active_cake_orders_in_slot(slot_key)
        if active_cake_orders >= self._slot_max_capacity:
            raise ValueError(
                f"该预约时段（{slot_key}）定制蛋糕接单已满，请选择其他时段"
            )

    @staticmethod
    def extract_slot_key(expect_time: str) -> str:
        """兼容转发：时段键实现已迁移到 cake_slots.extract_slot_key。"""
        return resolve_cake_slot_key(expect_time)

    async def _count_active_cake_orders_in_slot(self, slot_key: str) -> int:
        """统计某预约时段内当前活跃（未取消）的定制蛋糕订单数量。"""
        db = getattr(self._order_repo, "_db", None)
        if db is None:
            return 0
        date_prefix = slot_key.split(" ")[0] if " " in slot_key else slot_key
        rows = await db.execute_fetchall(
            "SELECT delivery, products FROM orders WHERE status != ? AND delivery LIKE ?",
            (OrderStatus.CANCELLED.value, f"%{date_prefix}%"),
        )
        count = 0
        for row in rows:
            if hasattr(row, "keys"):
                delivery_json = str(row["delivery"] if "delivery" in row.keys() else "")
                products_json = str(row["products"] if "products" in row.keys() else "")
            elif isinstance(row, (tuple, list)):
                delivery_json = str(row[0] if len(row) > 0 else "")
                products_json = str(row[1] if len(row) > 1 else "")
            else:
                delivery_json = str(getattr(row, "delivery", ""))
                products_json = str(getattr(row, "products", ""))

            order_expect = ""
            if "expectTime" in delivery_json:
                import json

                try:
                    d_dict = json.loads(delivery_json)
                    order_expect = str(d_dict.get("expectTime", ""))
                except Exception:
                    pass
            try:
                order_slot_key = (
                    resolve_cake_slot_key(order_expect) if order_expect else ""
                )
            except ValueError as exc:
                # 历史脏数据中的非法预约时间不参与容量统计。
                logger.debug("跳过非法预约时间订单容量统计: %s", exc)
                order_slot_key = ""
            if order_slot_key and order_slot_key == slot_key:
                # 检查该订单是否包含定制蛋糕（含定制信息、PREORDER_CAKE标识或定制关键词）
                if (
                    "customization" in products_json
                    or "PREORDER_CAKE" in products_json
                    or any(kw in products_json for kw in CAKE_KEYWORDS)
                ):
                    count += 1
        return count


__all__ = [
    "OrderFulfillmentDualTrackService",
    "FULFILLMENT_PREORDER_CAKE",
    "FULFILLMENT_DAILY_READY",
    "DEFAULT_CAKE_MIN_ADVANCE_HOURS",
    "DEFAULT_SLOT_MAX_CAPACITY",
]
