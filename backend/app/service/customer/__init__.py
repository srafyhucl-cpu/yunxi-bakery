"""客户领域服务导出。

该目录承载 Platform 的客户域 canonical 命名。
现阶段先通过兼容包装层复用既有实现，避免一次性改动现网行为。
"""

from app.service.customer.address import CustomerAddressService
from app.service.customer.group_operations import CustomerGroupOperationsService
from app.service.customer.importer import CustomerImportService
from app.service.customer.master import CustomerMasterService

__all__ = [
    "CustomerAddressService",
    "CustomerGroupOperationsService",
    "CustomerImportService",
    "CustomerMasterService",
]
