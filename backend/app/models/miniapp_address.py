"""小程序收货地址模型兼容入口。"""

from app.models.customer_address import (
    CustomerAddress as MiniappAddress,
    CustomerAddressAuditEntry as MiniappAddressAuditEntry,
)

__all__ = ["MiniappAddress", "MiniappAddressAuditEntry"]
