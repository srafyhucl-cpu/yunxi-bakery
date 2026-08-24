"""订单预约时间校验。"""

from datetime import datetime

from app.service.business_hours import (
    BusinessHours,
    is_inside_business_hours,
    parse_business_hours_or_default,
)
from app.service.shop_operations import ShopOperationsService

EXPECT_TIME_FORMAT = "%Y-%m-%d %H:%M"
DEFAULT_DELIVERY_TYPE = "pickup"


class OrderScheduleService:
    """校验并构建订单配送和预约信息。"""

    def __init__(self, shop_operations_service: ShopOperationsService) -> None:
        self._shop_operations_service = shop_operations_service

    async def build_delivery(self, payload: dict) -> dict:
        """构建订单配送信息，并确保预约时间可履约。"""
        expect_time = str(payload.get("expectTime", "")).strip()
        business_hours = await self._load_business_hours()
        self._validate_expect_time(expect_time, business_hours)
        return {
            "receiverName": str(payload.get("receiverName", "")).strip(),
            "receiverPhone": str(payload.get("receiverPhone", "")).strip(),
            "deliveryType": str(
                payload.get("deliveryType", DEFAULT_DELIVERY_TYPE)
            ).strip()
            or DEFAULT_DELIVERY_TYPE,
            "deliveryAddress": str(payload.get("deliveryAddress", "")).strip(),
            "expectTime": expect_time,
        }

    async def _load_business_hours(self) -> BusinessHours:
        operations = await self._shop_operations_service.get_shop_operations()
        raw_hours = str(operations.get("businessHours", "")).strip()
        return parse_business_hours_or_default(raw_hours)

    def _validate_expect_time(self, value: str, business_hours: BusinessHours) -> None:
        if not value:
            raise ValueError("预约时间不能为空")
        try:
            expect_time = datetime.strptime(value, EXPECT_TIME_FORMAT)
        except ValueError as exc:
            raise ValueError("预约时间格式应为 YYYY-MM-DD HH:mm") from exc
        if not is_inside_business_hours(expect_time.time(), business_hours):
            raise ValueError("预约时间不在营业时间内")


__all__ = ["DEFAULT_DELIVERY_TYPE", "EXPECT_TIME_FORMAT", "OrderScheduleService"]
