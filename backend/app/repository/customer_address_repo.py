"""客户地址数据访问层。"""

from app.models.customer_address import CustomerAddress
from app.repository.base import BaseRepository


class CustomerAddressRepo(BaseRepository):
    """按客户渠道身份隔离读写收货地址。"""

    async def list_by_user(self, user_id: str) -> list[CustomerAddress]:
        rows = await self._db.execute_fetchall(
            "SELECT id, user_id, receiver_name, receiver_phone, address, "
            "is_default, created_at, updated_at "
            "FROM miniapp_addresses WHERE user_id = ? "
            "ORDER BY is_default DESC, updated_at DESC",
            (user_id,),
        )
        return [CustomerAddress(**dict(row)) for row in rows]

    async def list_admin_addresses(
        self,
        *,
        keyword: str = "",
        limit: int = 30,
        offset: int = 0,
    ) -> list[CustomerAddress]:
        clauses, params = self._build_where(keyword)
        rows = await self._db.execute_fetchall(
            "SELECT id, user_id, receiver_name, receiver_phone, address, "
            "is_default, created_at, updated_at "
            "FROM miniapp_addresses WHERE " + " AND ".join(clauses) + " "
            "ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return [CustomerAddress(**dict(row)) for row in rows]

    async def count_admin_addresses(self, *, keyword: str = "") -> int:
        clauses, params = self._build_where(keyword)
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) AS c FROM miniapp_addresses WHERE "
            + " AND ".join(clauses),
            tuple(params),
        )
        return int(rows[0]["c"]) if rows else 0

    async def get_for_user(
        self, address_id: str, user_id: str
    ) -> CustomerAddress | None:
        rows = await self._db.execute_fetchall(
            "SELECT id, user_id, receiver_name, receiver_phone, address, "
            "is_default, created_at, updated_at "
            "FROM miniapp_addresses WHERE id = ? AND user_id = ? LIMIT 1",
            (address_id, user_id),
        )
        return CustomerAddress(**dict(rows[0])) if rows else None

    async def get(self, address_id: str) -> CustomerAddress | None:
        rows = await self._db.execute_fetchall(
            "SELECT id, user_id, receiver_name, receiver_phone, address, "
            "is_default, created_at, updated_at "
            "FROM miniapp_addresses WHERE id = ? LIMIT 1",
            (address_id,),
        )
        return CustomerAddress(**dict(rows[0])) if rows else None

    async def upsert(self, item: CustomerAddress) -> None:
        await self._db.execute(
            "INSERT INTO miniapp_addresses ("
            "id, user_id, receiver_name, receiver_phone, address, is_default, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "receiver_name = excluded.receiver_name, "
            "receiver_phone = excluded.receiver_phone, "
            "address = excluded.address, "
            "is_default = excluded.is_default, "
            "updated_at = excluded.updated_at "
            "WHERE miniapp_addresses.user_id = excluded.user_id",
            (
                item.id,
                item.user_id,
                item.receiver_name,
                item.receiver_phone,
                item.address,
                item.is_default,
                item.created_at,
                item.updated_at,
            ),
        )
        await self._db.commit()

    async def clear_default(self, user_id: str) -> None:
        await self._db.execute(
            "UPDATE miniapp_addresses SET is_default = 0 WHERE user_id = ?",
            (user_id,),
        )
        await self._db.commit()

    async def set_default(
        self, address_id: str, user_id: str, updated_at: str
    ) -> CustomerAddress | None:
        await self._db.execute(
            "UPDATE miniapp_addresses SET is_default = 1, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            (updated_at, address_id, user_id),
        )
        await self._db.commit()
        return await self.get_for_user(address_id, user_id)

    async def delete_for_user(
        self, address_id: str, user_id: str
    ) -> CustomerAddress | None:
        item = await self.get_for_user(address_id, user_id)
        if not item:
            return None
        await self._db.execute(
            "DELETE FROM miniapp_addresses WHERE id = ? AND user_id = ?",
            (address_id, user_id),
        )
        await self._db.commit()
        return item

    def _build_where(self, keyword: str) -> tuple[list[str], list[object]]:
        clauses = ["1 = 1"]
        params: list[object] = []
        if keyword:
            like = f"%{keyword}%"
            clauses.append(
                "(id LIKE ? OR user_id LIKE ? OR receiver_name LIKE ? "
                "OR receiver_phone LIKE ? OR address LIKE ?)"
            )
            params.extend([like, like, like, like, like])
        return clauses, params


__all__ = ["CustomerAddressRepo"]
