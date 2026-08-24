"""小程序地址簿服务测试。"""

import aiosqlite
import pytest

from app.repository.customer_address_repo import CustomerAddressRepo
from app.service.customer import CustomerAddressService


@pytest.fixture
def service(db: aiosqlite.Connection) -> CustomerAddressService:
    """使用真实内存库仓储构建地址簿服务。"""
    return CustomerAddressService(CustomerAddressRepo(db))


async def test_first_address_becomes_default(service: CustomerAddressService) -> None:
    """首个地址自动成为默认地址。"""
    saved = await service.save_address(
        {
            "receiverName": "地址测试",
            "receiverPhone": "18800000001",
            "address": "测试路 1 号",
        },
        user_id="address-user",
    )

    items = await service.list_addresses("address-user")

    assert saved["isDefault"] is True
    assert items[0]["id"] == saved["id"]
    assert items[0]["isDefault"] is True


async def test_default_address_is_unique(service: CustomerAddressService) -> None:
    """设置默认地址后，同一用户只能保留一个默认地址。"""
    first = await service.save_address(
        {
            "id": "addr-first",
            "receiverName": "默认一",
            "receiverPhone": "18800000002",
            "address": "测试路 2 号",
        },
        user_id="default-user",
    )
    second = await service.save_address(
        {
            "id": "addr-second",
            "receiverName": "默认二",
            "receiverPhone": "18800000003",
            "address": "测试路 3 号",
            "isDefault": True,
        },
        user_id="default-user",
    )

    items = await service.list_addresses("default-user")

    assert first["isDefault"] is True
    assert second["isDefault"] is True
    assert [item["id"] for item in items if item["isDefault"]] == ["addr-second"]


async def test_user_cannot_set_other_users_address_default(
    service: CustomerAddressService,
) -> None:
    """地址默认切换必须校验用户归属。"""
    await service.save_address(
        {
            "id": "addr-owner-only",
            "receiverName": "归属测试",
            "receiverPhone": "18800000004",
            "address": "归属路 4 号",
        },
        user_id="owner-user",
    )

    with pytest.raises(ValueError, match="地址不存在"):
        await service.set_default("addr-owner-only", user_id="other-user")


async def test_delete_default_promotes_next_address(
    service: CustomerAddressService,
) -> None:
    """删除默认地址后，剩余地址应自动补一个默认地址。"""
    await service.save_address(
        {
            "id": "addr-delete-default",
            "receiverName": "删除一",
            "receiverPhone": "18800000005",
            "address": "删除路 5 号",
        },
        user_id="delete-user",
    )
    await service.save_address(
        {
            "id": "addr-delete-next",
            "receiverName": "删除二",
            "receiverPhone": "18800000006",
            "address": "删除路 6 号",
        },
        user_id="delete-user",
    )

    items = await service.delete_address("addr-delete-default", user_id="delete-user")

    assert [item["id"] for item in items] == ["addr-delete-next"]
    assert items[0]["isDefault"] is True


async def test_rejects_invalid_phone(service: CustomerAddressService) -> None:
    """保存地址时应校验大陆手机号格式。"""
    with pytest.raises(ValueError, match="请填写正确的 11 位手机号"):
        await service.save_address(
            {
                "receiverName": "号码测试",
                "receiverPhone": "123",
                "address": "号码路 7 号",
            },
            user_id="invalid-phone-user",
        )
