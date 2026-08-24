"""退款操作事实（refund_operation）数据访问层（B3.5，评审问题 3）。

每次已结算退款记录一条退款操作事实（operation_key 幂等）：
- 已结算订单的每次退款补偿（return / clawback）与其事实快照、案件同一事务；
- 补偿未终结（存在 open 案件或欠账）时不清除事实快照，保证可重试；
- 人工结清欠账后由对账工序按 operation_key 关联结案。
"""

from app.repository.base import BaseRepository
from app.utils import now_str

REFUND_OP_SUCCEEDED = "succeeded"
REFUND_OP_PARTIAL = "partial"
REFUND_OP_SHORTFALL = "shortfall"


class RefundOperationRepo(BaseRepository):
    """退款操作事实仓储（只追加，operation_key 幂等）。"""

    async def append(
        self,
        *,
        order_id: str,
        mobile: str,
        member_balance_id: int | None,
        operation_key: str,
        points_used: int,
        points_awarded: int,
        return_amount: int,
        clawback_amount: int,
        shortfall_amount: int,
        status: str,
        note: str = "",
    ) -> bool:
        """追加一条退款操作事实；同 operation_key 幂等，返回是否新增。"""
        timestamp = now_str()
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO refund_operation "
            "(order_id, mobile, member_balance_id, operation_key, points_used, "
            "points_awarded, return_amount, clawback_amount, shortfall_amount, "
            "status, note, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                order_id,
                mobile,
                member_balance_id,
                operation_key,
                points_used,
                points_awarded,
                return_amount,
                clawback_amount,
                shortfall_amount,
                status,
                note,
                timestamp,
                timestamp,
            ),
        )
        return int(cursor.rowcount or 0) > 0

    async def get_by_operation_key(self, operation_key: str) -> dict | None:
        """按操作幂等键读取退款操作事实。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, order_id, mobile, member_balance_id, operation_key, "
            "points_used, points_awarded, return_amount, clawback_amount, "
            "shortfall_amount, status, note, created_at, updated_at "
            "FROM refund_operation WHERE operation_key = ? LIMIT 1",
            (operation_key,),
        )
        return rows[0] if rows else None


__all__ = [
    "RefundOperationRepo",
    "REFUND_OP_PARTIAL",
    "REFUND_OP_SHORTFALL",
    "REFUND_OP_SUCCEEDED",
]
