"""营业时间解析与校验。"""

from dataclasses import dataclass
from datetime import datetime, time

from app.models.config import DEFAULT_SHOP_OPERATIONS

BUSINESS_HOURS_FORMAT_ERROR = "营业时间格式应为 HH:mm-HH:mm"
BUSINESS_HOURS_ORDER_ERROR = "营业时间结束时间必须晚于开始时间"
BUSINESS_HOURS_SEPARATOR = "-"
MINUTES_PER_HOUR = 60


@dataclass(frozen=True)
class BusinessHours:
    """同日营业时间范围。"""

    start: time
    end: time


def parse_business_hours(value: str) -> BusinessHours:
    """解析营业时间，非法时抛出可展示错误。"""
    if BUSINESS_HOURS_SEPARATOR not in value:
        raise ValueError(BUSINESS_HOURS_FORMAT_ERROR)
    parts = [part.strip() for part in value.split(BUSINESS_HOURS_SEPARATOR, 1)]
    try:
        start = datetime.strptime(parts[0], "%H:%M").time()
        end = datetime.strptime(parts[1], "%H:%M").time()
    except ValueError as exc:
        raise ValueError(BUSINESS_HOURS_FORMAT_ERROR) from exc
    if _to_minutes(end) <= _to_minutes(start):
        raise ValueError(BUSINESS_HOURS_ORDER_ERROR)
    return BusinessHours(start=start, end=end)


def parse_business_hours_or_default(value: str) -> BusinessHours:
    """解析营业时间，非法配置回退默认值。"""
    try:
        return parse_business_hours(value)
    except ValueError:
        return parse_business_hours(DEFAULT_SHOP_OPERATIONS["businessHours"])


def is_inside_business_hours(value: time, business_hours: BusinessHours) -> bool:
    """判断指定时刻是否落在同日营业时间内。"""
    value_minutes = _to_minutes(value)
    return (
        _to_minutes(business_hours.start)
        <= value_minutes
        <= _to_minutes(business_hours.end)
    )


def _to_minutes(value: time) -> int:
    return value.hour * MINUTES_PER_HOUR + value.minute
