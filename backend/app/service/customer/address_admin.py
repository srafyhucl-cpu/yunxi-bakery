"""客户地址后台管理协同器。"""

from typing import Any

from app.repository.customer_address_audit_repo import CustomerAddressAuditRepo
from app.repository.customer_address_repo import CustomerAddressRepo
from app.service.customer.address_support import (
    build_address,
    build_audit_entry,
    serialize_address,
    serialize_audit,
    utc_now,
)


class CustomerAddressAdminCoordinator:
    """承接后台地址分页、审计与后台写操作。"""

    def __init__(
        self,
        address_repo: CustomerAddressRepo,
        audit_repo: CustomerAddressAuditRepo | None = None,
    ) -> None:
        self._address_repo = address_repo
        self._audit_repo = audit_repo

    async def list_admin_addresses(
        self,
        *,
        page: int = 1,
        keyword: str = "",
    ) -> dict[str, Any]:
        page_size = 30
        current_page = max(1, int(page or 1))
        normalized_keyword = keyword.strip()
        items = await self._address_repo.list_admin_addresses(
            keyword=normalized_keyword,
            limit=page_size,
            offset=(current_page - 1) * page_size,
        )
        total = await self._address_repo.count_admin_addresses(
            keyword=normalized_keyword
        )
        return {
            "items": [serialize_address(item, include_user=True) for item in items],
            "total": total,
            "page": current_page,
            "pageSize": page_size,
        }

    async def get_admin_address(self, address_id: str) -> dict[str, Any]:
        item = await self._address_repo.get(address_id)
        if not item:
            raise ValueError("地址不存在")
        return {
            **serialize_address(item, include_user=True),
            "auditLogs": await self.list_admin_address_audit(address_id),
        }

    async def list_admin_address_audit(self, address_id: str) -> list[dict[str, Any]]:
        if self._audit_repo is None:
            return []
        entries = await self._audit_repo.list_by_address(address_id, limit=5)
        return [serialize_audit(entry) for entry in entries]

    async def save_admin_address(
        self,
        payload: dict[str, Any],
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        user_id = str(payload.get("userId", "")).strip()
        if not user_id:
            raise ValueError("请填写用户标识")
        address_id = str(payload.get("id", "")).strip()
        existing = (
            await self._address_repo.get_for_user(address_id, user_id)
            if address_id
            else None
        )
        if address_id and not existing:
            raise ValueError("地址不存在")
        current_items = await self._address_repo.list_by_user(user_id)
        build_payload = dict(payload)
        if existing:
            build_payload["createdAt"] = existing.created_at
        item = build_address(build_payload, user_id, should_default=not current_items)
        if item.is_default:
            await self._address_repo.clear_default(user_id)
        await self._address_repo.upsert(item)
        await self._add_audit_log(
            action="update" if existing else "create",
            address_id=item.id,
            user_id=user_id,
            operator=operator,
            before=serialize_address(existing, include_user=True) if existing else None,
            after=serialize_address(item, include_user=True),
            note="后台新增地址" if existing is None else "后台编辑地址",
        )
        return serialize_address(item, include_user=True)

    async def set_admin_default(
        self,
        address_id: str,
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        item = await self._address_repo.get(address_id)
        if not item:
            raise ValueError("地址不存在")
        before = serialize_address(item, include_user=True)
        await self._address_repo.clear_default(item.user_id)
        updated = await self._address_repo.set_default(
            address_id, item.user_id, utc_now()
        )
        if not updated:
            raise ValueError("地址不存在")
        await self._add_audit_log(
            action="set_default",
            address_id=address_id,
            user_id=item.user_id,
            operator=operator,
            before=before,
            after=serialize_address(updated, include_user=True),
            note="后台设为默认地址",
        )
        return serialize_address(updated, include_user=True)

    async def delete_admin_address(
        self,
        address_id: str,
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        item = await self._address_repo.get(address_id)
        if not item:
            raise ValueError("地址不存在")
        deleted = await self._address_repo.delete_for_user(address_id, item.user_id)
        if not deleted:
            raise ValueError("地址不存在")
        await self._normalize_user_default(item.user_id)
        await self._add_audit_log(
            action="delete",
            address_id=address_id,
            user_id=item.user_id,
            operator=operator,
            before=serialize_address(deleted, include_user=True),
            after=None,
            note="后台删除地址",
        )
        return serialize_address(deleted, include_user=True)

    async def _normalize_user_default(self, user_id: str) -> None:
        items = await self._address_repo.list_by_user(user_id)
        if not items:
            return
        default_count = sum(1 for item in items if item.is_default)
        if default_count == 1:
            return
        default_item = items[0]
        await self._address_repo.clear_default(user_id)
        await self._address_repo.set_default(default_item.id, user_id, utc_now())

    async def _add_audit_log(
        self,
        *,
        action: str,
        address_id: str,
        user_id: str,
        operator: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        note: str,
    ) -> None:
        if self._audit_repo is None:
            return
        await self._audit_repo.add(
            build_audit_entry(
                action=action,
                address_id=address_id,
                user_id=user_id,
                operator=operator,
                before=before,
                after=after,
                note=note,
            )
        )
