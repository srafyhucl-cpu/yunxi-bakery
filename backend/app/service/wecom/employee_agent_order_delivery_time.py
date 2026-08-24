"""企微员工助手订单配送时间段解析。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryTimeWindow:
    """订单配送时间段查询边界。"""

    start: str
    end: str


DELIVERY_TIME_WINDOWS = {
    "凌晨": DeliveryTimeWindow("00:00", "05:59"),
    "早上": DeliveryTimeWindow("06:00", "10:59"),
    "上午": DeliveryTimeWindow("06:00", "11:59"),
    "中午": DeliveryTimeWindow("11:00", "13:59"),
    "下午": DeliveryTimeWindow("12:00", "17:59"),
    "傍晚": DeliveryTimeWindow("17:00", "19:59"),
    "晚上": DeliveryTimeWindow("18:00", "23:59"),
    "夜里": DeliveryTimeWindow("18:00", "23:59"),
}


def resolve_delivery_time_window(query: str) -> DeliveryTimeWindow | None:
    """把员工口语配送时段转成白名单时间窗。"""
    for keyword, window in DELIVERY_TIME_WINDOWS.items():
        if keyword in query:
            return window
    return None


def remove_delivery_time_expressions(query: str) -> str:
    """移除配送时段词，避免污染商品关键词。"""
    keyword = query
    for window_keyword in DELIVERY_TIME_WINDOWS:
        keyword = keyword.replace(window_keyword, " ")
    return keyword
