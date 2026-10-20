"""储值余额流水数据访问层。"""

from app.models.stored_value import BalanceLedgerEntry
from app.repository.base import BaseRepository


class BalanceLedgerRepo(BaseRepository):
    """储值流水仓储（unique_id 幂等去重）。"""

    LEDGER_COLUMNS = (
        "id, unique_id, user_id, mobile, customer_id, amount_fen, "
        "balance_after_fen, biz_type, biz_id, source, occurred_at, created_at, "
        "request_fingerprint, principal_delta_fen, bonus_delta_fen"
    )

    async def insert(self, entry: BalanceLedgerEntry) -> bool:
        """写入一条流水，重复 unique_id 幂等跳过。

        请求指纹与本金的拆分随正式插入一次落库，不存在先空后补窗口。
        """
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO balance_ledger (unique_id, user_id, mobile, "
            "customer_id, amount_fen, balance_after_fen, biz_type, biz_id, source, "
            "occurred_at, request_fingerprint, principal_delta_fen, bonus_delta_fen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                entry.request_fingerprint,
                entry.principal_delta_fen,
                entry.bonus_delta_fen,
            ),
        )
        return bool(cursor.rowcount == 1)

    async def insert_placeholder(self, entry: BalanceLedgerEntry) -> bool:
        """幂等占位先行，返回是否抢到本次记账权。

        调用方须在同一事务内完成余额变更后补写余额快照；
        未抢到时调用方按已存在流水做重放校验，不得重复变更余额。
        """
        return await self.insert(entry)

    async def complete_placeholder(
        self,
        unique_id: str,
        balance_after_fen: int,
        principal_delta_fen: int | None = None,
        bonus_delta_fen: int | None = None,
    ) -> None:
        """补写占位流水的余额快照与本金/赠送金拆分，与余额变更同一事务提交。

        扣款的实际拆分在余额变更时才确定（优先扣赠送金），因此在此补写；
        未传入拆分时保留占位值，兼容只补余额快照的调用方。
        """
        await self._db.execute(
            "UPDATE balance_ledger SET balance_after_fen = ?, "
            "principal_delta_fen = COALESCE(?, principal_delta_fen), "
            "bonus_delta_fen = COALESCE(?, bonus_delta_fen) WHERE unique_id = ?",
            (balance_after_fen, principal_delta_fen, bonus_delta_fen, unique_id),
        )

    async def delete_placeholder(self, unique_id: str) -> None:
        """删除占位流水，用于余额不足等未发生变更的回退。"""
        await self._db.execute(
            "DELETE FROM balance_ledger WHERE unique_id = ?",
            (unique_id,),
        )

    async def get_by_unique_id(self, unique_id: str) -> dict | None:
        """按幂等键读取流水。"""
        rows = await self._db.execute_fetchall(
            "SELECT "
            + self.LEDGER_COLUMNS
            + " FROM balance_ledger WHERE unique_id = ? LIMIT 1",
            (unique_id,),
        )
        return dict(rows[0]) if rows else None

    async def list_by_mobile(self, mobile: str, *, limit: int = 50) -> list[dict]:
        """按手机号读取最近流水。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + self.LEDGER_COLUMNS + " FROM balance_ledger WHERE mobile = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (mobile, limit),
        )
        return [dict(row) for row in rows]

    async def count_after_id(self, mobile: str, ledger_id: int) -> int:
        """统计同一会员在该流水之后新增的流水条数（回滚干净性判定）。"""
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(id) AS entry_count FROM balance_ledger "
            "WHERE mobile = ? AND id > ?",
            (mobile, ledger_id),
        )
        return int(rows[0]["entry_count"]) if rows else 0

    async def sum_split_by_biz(self, *, biz_type: str, biz_id: str) -> dict:
        """按业务归属汇总流水的总额与本金/赠送金拆分（批次对账使用）。

        仅看总额无法证明拆分结构正确，故一次返回三项合计，供报告分别核对
        principal_delta_fen / bonus_delta_fen 是否与本批次期初值一致。
        """
        rows = await self._db.execute_fetchall(
            "SELECT COALESCE(SUM(amount_fen), 0) AS total_fen, "
            "COALESCE(SUM(principal_delta_fen), 0) AS principal_fen, "
            "COALESCE(SUM(bonus_delta_fen), 0) AS bonus_fen FROM balance_ledger "
            "WHERE biz_type = ? AND biz_id = ?",
            (biz_type, biz_id),
        )
        if not rows:
            return {"total_fen": 0, "principal_fen": 0, "bonus_fen": 0}
        return {
            "total_fen": int(rows[0]["total_fen"]),
            "principal_fen": int(rows[0]["principal_fen"]),
            "bonus_fen": int(rows[0]["bonus_fen"]),
        }

    async def delete_by_unique_id(self, unique_id: str) -> int:
        """按幂等键删除流水，返回删除条数（期初导入回滚使用）。"""
        cursor = await self._db.execute(
            "DELETE FROM balance_ledger WHERE unique_id = ?",
            (unique_id,),
        )
        return int(cursor.rowcount)
