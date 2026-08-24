"""店铺运营配置服务兼容包装。"""

from app.service.shop_operations import (
    ShopOperationsService as ShopConfigurationService,
)

__all__ = ["ShopConfigurationService"]
