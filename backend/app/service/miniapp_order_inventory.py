"""小程序订单库存协作兼容入口。"""

from app.service.order.inventory import (
    NormalizedOrderItem,
    OrderInventoryService as MiniappOrderInventoryService,
)


__all__ = ["MiniappOrderInventoryService", "NormalizedOrderItem"]
