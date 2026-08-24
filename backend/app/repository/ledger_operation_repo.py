"""结算事实（ledger_operation）数据访问层（B3.5，评审问题 2）。

结算事实与积分流水、支付快照 pointsSettledAt 标记同一 UoW 原子提交：
崩溃前「流水已写、标记未写」的窗口不再存在，未结算判定不再误判。
"""

from app.repository.base import BaseRepository
from app.utils import now_str

SETTLE_REDEEM = "settle_redeem"
SETTLE_AWARD = "settle_award"
REFUND_RETURN = "refund_return"
REFUND_CLAWBACK = "refund_clawback"


class LedgerOperationRepo(BaseRepository):
    """结算事实仓储（只追加，unique_id 幂等）。"""

    async def append(
        self,
        *,
        operation_type: str,
        subject_id: str,
        mobile: str,
        member_balance_id: int | None,
        amount: int,
        unique_id: str,
        biz_type: str = "",
        biz_id: str = "",
        subject_type: str = "order",
    ) -> bool:
        """追加一条结算事实；同 unique_id 幂等，返回是否新增。"""
        timestamp = now_str()
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO ledger_operation "
            "(operation_type, subject_type, subject_id, mobile, member_balance_id, "
            "amount, unique_id, biz_type, biz_id, occurred_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                operation_type,
                subject_type,
                subject_id,
                mobile,
                member_balance_id,
                amount,
                unique_id,
                biz_type,
                biz_id,
                timestamp,
                timestamp,
            ),
        )
        return int(cursor.rowcount or 0) > 0

    async def get_by_unique_id(self, unique_id: str) -> dict | None:
        """按幂等键读取结算事实。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, operation_type, subject_type, subject_id, mobile, "
            "member_balance_id, amount, unique_id, biz_type, biz_id, "
            "occurred_at, created_at FROM ledger_operation "
            "WHERE unique_id = ? LIMIT 1",
            (unique_id,),
        )
        return rows[0] if rows else None

    async def list_by_subject(self, subject_id: str) -> list[dict]:
        """读取某主体的全部结算事实（按发生时间升序）。"""
        return await self._db.execute_fetchall(
            "SELECT id, operation_type, subject_type, subject_id, mobile, "
            "member_balance_id, amount, unique_id, biz_type, biz_id, "
            "occurred_at, created_at FROM ledger_operation "
            "WHERE subject_type = 'order' AND subject_id = ? ORDER BY id ASC",
            (subject_id,),
        )


__all__ = [
    "LedgerOperationRepo",
    "REFUND_CLAWBACK",
    "REFUND_RETURN",
    "SETTLE_AWARD",
    "SETTLE_REDEEM",
]
