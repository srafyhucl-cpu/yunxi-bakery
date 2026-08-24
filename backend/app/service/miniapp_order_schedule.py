"""小程序订单预约时间兼容入口。"""

from app.service.order.schedule import (
    DEFAULT_DELIVERY_TYPE,
    EXPECT_TIME_FORMAT,
    OrderScheduleService as MiniappOrderScheduleService,
)


__all__ = [
    "DEFAULT_DELIVERY_TYPE",
    "EXPECT_TIME_FORMAT",
    "MiniappOrderScheduleService",
]
