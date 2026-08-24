"""客户地址领域服务。"""

from typing import Any

from app.repository.customer_address_repo import CustomerAddressRepo
from app.service.customer.address_admin import CustomerAddressAdminCoordinator
from app.service.customer.address_support import (
    build_address,
    serialize_address,
    utc_now,
)


class CustomerAddressService:
    """管理客户地址簿与后台地址审计。"""

    def __init__(
        self,
        address_repo: CustomerAddressRepo,
        audit_repo=None,
    ) -> None:
        self._address_repo = address_repo
        self._admin = CustomerAddressAdminCoordinator(address_repo, audit_repo)

    async def list_addresses(self, user_id: str) -> list[dict[str, Any]]:
        items = await self._address_repo.list_by_user(user_id)
        normalized_items = await self._ensure_default(items, user_id)
        return [serialize_address(item) for item in normalized_items]

    async def list_admin_addresses(
        self,
        *,
        page: int = 1,
        keyword: str = "",
    ) -> dict[str, Any]:
        return await self._admin.list_admin_addresses(page=page, keyword=keyword)

    async def get_admin_address(self, address_id: str) -> dict[str, Any]:
        return await self._admin.get_admin_address(address_id)

    async def list_admin_address_audit(self, address_id: str) -> list[dict[str, Any]]:
        return await self._admin.list_admin_address_audit(address_id)

    async def save_admin_address(
        self,
        payload: dict[str, Any],
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        return await self._admin.save_admin_address(payload, operator=operator)

    async def save_address(
        self,
        payload: dict[str, Any],
        user_id: str,
    ) -> dict[str, Any]:
        current_items = await self._address_repo.list_by_user(user_id)
        item = build_address(payload, user_id, should_default=not current_items)
        if item.is_default:
            await self._address_repo.clear_default(user_id)
        await self._address_repo.upsert(item)
        return serialize_address(item)

    async def set_default(self, address_id: str, user_id: str) -> dict[str, Any]:
        existing = await self._address_repo.get_for_user(address_id, user_id)
        if not existing:
            raise ValueError("地址不存在")
        await self._address_repo.clear_default(user_id)
        updated = await self._address_repo.set_default(address_id, user_id, utc_now())
        if not updated:
            raise ValueError("地址不存在")
        return serialize_address(updated)

    async def set_admin_default(
        self,
        address_id: str,
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        return await self._admin.set_admin_default(address_id, operator=operator)

    async def delete_address(
        self,
        address_id: str,
        user_id: str,
    ) -> list[dict[str, Any]]:
        deleted = await self._address_repo.delete_for_user(address_id, user_id)
        if not deleted:
            raise ValueError("地址不存在")
        items = await self._address_repo.list_by_user(user_id)
        normalized_items = await self._ensure_default(items, user_id)
        return [serialize_address(item) for item in normalized_items]

    async def delete_admin_address(
        self,
        address_id: str,
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        return await self._admin.delete_admin_address(address_id, operator=operator)

    async def _ensure_default(
        self,
        items: list,
        user_id: str,
    ) -> list:
        if not items:
            return []
        default_count = sum(1 for item in items if item.is_default)
        if default_count == 1:
            return items
        default_item = items[0]
        await self._address_repo.clear_default(user_id)
        updated_default = await self._address_repo.set_default(
            default_item.id,
            user_id,
            utc_now(),
        )
        if updated_default:
            return await self._address_repo.list_by_user(user_id)
        return items
