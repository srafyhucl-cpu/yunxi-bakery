"""订单预约时间校验。"""

from collections.abc import Callable
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.service.business_hours import (
    BusinessHours,
    is_inside_business_hours,
    parse_business_hours_or_default,
)
from app.service.shop_operations import ShopOperationsService

EXPECT_TIME_FORMAT = "%Y-%m-%d %H:%M"
DEFAULT_DELIVERY_TYPE = "pickup"
BEIJING_DELIVERY_TYPE = "beijing_delivery"
LEGACY_DELIVERY_TYPE = "delivery"
BEIJING_TIME_ZONE = ZoneInfo("Asia/Shanghai")
SAME_DAY_ORDER_CUTOFF = time(17, 0)


class OrderScheduleService:
    """校验并构建订单配送和预约信息。"""

    def __init__(
        self,
        shop_operations_service: ShopOperationsService,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._shop_operations_service = shop_operations_service
        self._now_provider = now_provider or _get_current_beijing_time

    async def build_delivery(self, payload: dict) -> dict:
        """构建订单配送信息，并确保预约时间可履约。"""
        expect_time = str(payload.get("expectTime", "")).strip()
        await self.validate_expect_time(expect_time)
        fulfillment_method = self._resolve_fulfillment_method(payload)
        delivery_dict = {
            "receiverName": str(payload.get("receiverName", "")).strip(),
            "receiverPhone": str(payload.get("receiverPhone", "")).strip(),
            "deliveryType": fulfillment_method,
            "fulfillmentMethod": fulfillment_method,
            "pickupAddress": str(payload.get("pickupAddress", "")).strip(),
            "deliveryAddress": str(payload.get("deliveryAddress", "")).strip(),
            "expectTime": expect_time,
        }
        delivery_quote_id = str(payload.get("deliveryQuoteId", "")).strip()
        if delivery_quote_id:
            delivery_dict["deliveryQuoteId"] = delivery_quote_id
        return delivery_dict

    @staticmethod
    def _resolve_fulfillment_method(payload: dict) -> str:
        requested = (
            str(
                payload.get(
                    "fulfillmentMethod",
                    payload.get("deliveryType", DEFAULT_DELIVERY_TYPE),
                )
            ).strip()
            or DEFAULT_DELIVERY_TYPE
        )
        if requested == LEGACY_DELIVERY_TYPE:
            return BEIJING_DELIVERY_TYPE
        if requested in (DEFAULT_DELIVERY_TYPE, BEIJING_DELIVERY_TYPE):
            return requested
        raise ValueError("不支持的履约方式")

    async def _load_business_hours(self) -> BusinessHours:
        operations = await self._shop_operations_service.get_shop_operations()
        raw_hours = str(operations.get("businessHours", "")).strip()
        return parse_business_hours_or_default(raw_hours)

    async def validate_expect_time(self, value: str) -> None:
        """校验预约时间满足当前截单点与营业时段。"""
        business_hours = await self._load_business_hours()
        validate_expect_time_value(value, business_hours, self._now_provider())


def validate_expect_time_value(
    value: str,
    business_hours: BusinessHours,
    current_time: datetime,
) -> None:
    """校验预约时间字符串，供订单与群内登记共享同一履约规则。"""
    if not value:
        raise ValueError("预约时间不能为空")
    try:
        expect_time = datetime.strptime(value, EXPECT_TIME_FORMAT)
    except ValueError as exc:
        raise ValueError("预约时间格式应为 YYYY-MM-DD HH:mm") from exc
    normalized_current_time = _normalize_beijing_time(current_time)
    if expect_time < normalized_current_time.replace(tzinfo=None):
        raise ValueError("预约时间不能早于当前时间")
    if (
        expect_time.date() == normalized_current_time.date()
        and normalized_current_time.time() >= SAME_DAY_ORDER_CUTOFF
    ):
        raise ValueError("当天订单已于 17:00 截止，请选择明天或更晚时间")
    if not is_inside_business_hours(expect_time.time(), business_hours):
        raise ValueError("预约时间不在营业时间内")


def _get_current_beijing_time() -> datetime:
    return datetime.now(BEIJING_TIME_ZONE)


def _normalize_beijing_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=BEIJING_TIME_ZONE)
    return value.astimezone(BEIJING_TIME_ZONE)


__all__ = [
    "BEIJING_DELIVERY_TYPE",
    "BEIJING_TIME_ZONE",
    "DEFAULT_DELIVERY_TYPE",
    "EXPECT_TIME_FORMAT",
    "OrderScheduleService",
    "SAME_DAY_ORDER_CUTOFF",
    "validate_expect_time_value",
]
