"""小程序收货地址数据访问层兼容入口。"""

from app.repository.customer_address_repo import (
    CustomerAddressRepo as MiniappAddressRepo,
)


__all__ = ["MiniappAddressRepo"]
