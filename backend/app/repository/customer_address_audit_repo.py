"""客户地址操作审计数据访问层。"""

from app.models.customer_address import CustomerAddressAuditEntry
from app.repository.base import BaseRepository


class CustomerAddressAuditRepo(BaseRepository):
    """保存和查询后台地址操作记录。"""

    async def add(self, entry: CustomerAddressAuditEntry) -> int:
        cursor = await self._db.execute(
            "INSERT INTO miniapp_address_audit ("
            "address_id, user_id, operator, action, before_json, after_json, note, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.address_id,
                entry.user_id,
                entry.operator,
                entry.action,
                entry.before_json,
                entry.after_json,
                entry.note,
                entry.created_at,
            ),
        )
        await self._db.commit()
        return int(cursor.lastrowid)

    async def list_by_address(
        self,
        address_id: str,
        *,
        limit: int = 5,
    ) -> list[CustomerAddressAuditEntry]:
        rows = await self._db.execute_fetchall(
            "SELECT id, address_id, user_id, operator, action, before_json, after_json, note, created_at "
            "FROM miniapp_address_audit WHERE address_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (address_id, limit),
        )
        return [CustomerAddressAuditEntry(**dict(row)) for row in rows]


__all__ = ["CustomerAddressAuditRepo"]
