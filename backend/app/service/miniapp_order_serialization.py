"""小程序订单序列化兼容入口。"""

from app.service.order.serialization import (
    OrderSerializationService as MiniappOrderSerializationService,
)


__all__ = ["MiniappOrderSerializationService"]
