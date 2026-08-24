"""储值余额流水数据访问层。"""

from app.models.stored_value import BalanceLedgerEntry
from app.repository.base import BaseRepository


class BalanceLedgerRepo(BaseRepository):
    """储值流水仓储（unique_id 幂等去重）。"""

    LEDGER_COLUMNS = (
        "id, unique_id, user_id, mobile, customer_id, amount_fen, "
        "balance_after_fen, biz_type, biz_id, source, occurred_at, created_at"
    )

    async def insert(self, entry: BalanceLedgerEntry) -> bool:
        """写入一条流水，重复 unique_id 幂等跳过。"""
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO balance_ledger (unique_id, user_id, mobile, "
            "customer_id, amount_fen, balance_after_fen, biz_type, biz_id, source, "
            "occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.unique_id,
                entry.user_id,
                entry.mobile,
                entry.customer_id,
                entry.amount_fen,
                entry.balance_after_fen,
                entry.biz_type,
                entry.biz_id,
                entry.source,
                entry.occurred_at,
            ),
        )
        return bool(cursor.rowcount == 1)

    async def get_by_unique_id(self, unique_id: str) -> dict | None:
        """按幂等键读取流水。"""
        rows = await self._db.execute_fetchall(
            "SELECT "
            + self.LEDGER_COLUMNS
            + " FROM balance_ledger WHERE unique_id = ? LIMIT 1",
            (unique_id,),
        )
        return rows[0] if rows else None

    async def list_by_mobile(self, mobile: str, *, limit: int = 50) -> list[dict]:
        """按手机号读取最近流水。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + self.LEDGER_COLUMNS + " FROM balance_ledger WHERE mobile = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (mobile, limit),
        )
        return [dict(row) for row in rows]
