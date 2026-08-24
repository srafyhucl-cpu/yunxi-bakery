"""小程序订单超时调度兼容入口。"""

from app.service.ops.order_timeout_scheduler import (
    OrderTimeoutScheduler as MiniappOrderTimeoutScheduler,
    SupportsOrderTimeoutScan as SupportsMiniappOrderTimeoutScan,
    register_order_timeout_scheduler as register_miniapp_order_timeout_scheduler,
    stop_order_timeout_scheduler as stop_miniapp_order_timeout_scheduler,
)


__all__ = [
    "MiniappOrderTimeoutScheduler",
    "SupportsMiniappOrderTimeoutScan",
    "register_miniapp_order_timeout_scheduler",
    "stop_miniapp_order_timeout_scheduler",
]
