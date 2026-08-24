"""小程序地址操作审计数据访问层兼容入口。"""

from app.repository.customer_address_audit_repo import (
    CustomerAddressAuditRepo as MiniappAddressAuditRepo,
)

__all__ = ["MiniappAddressAuditRepo"]
