"""奖励积分扣回欠账（refund_shortfall_debt）数据访问层（B3.5，评审问题 3）。

已结算退款收回奖励积分时余额不足（clawback 扣减返回 None），不得静默跳过：
写入欠账（operation_key 幂等，与退款操作事实关联），补偿未终结前
保留事实快照供重试；人工补足后由对账工序结清（status open→settled）。
"""

from app.repository.base import BaseRepository
from app.utils import now_str


class RefundShortfallDebtRepo(BaseRepository):
    """奖励积分扣回欠账仓储（只追加，operation_key 幂等）。"""

    async def append(
        self,
        *,
        order_id: str,
        mobile: str,
        member_balance_id: int | None,
        operation_key: str,
        amount: int,
        note: str = "",
    ) -> bool:
        """追加一条欠账；同 operation_key 幂等，返回是否新增。"""
        timestamp = now_str()
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO refund_shortfall_debt "
            "(order_id, mobile, member_balance_id, operation_key, amount, status, "
            "note, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)",
            (
                order_id,
                mobile,
                member_balance_id,
                operation_key,
                amount,
                note,
                timestamp,
                timestamp,
            ),
        )
        return int(cursor.rowcount or 0) > 0

    async def get_by_operation_key(self, operation_key: str) -> dict | None:
        """按操作幂等键读取欠账。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, order_id, mobile, member_balance_id, operation_key, amount, "
            "status, note, created_at, updated_at FROM refund_shortfall_debt "
            "WHERE operation_key = ? LIMIT 1",
            (operation_key,),
        )
        return rows[0] if rows else None

    async def list_open_by_order(self, order_id: str) -> list[dict]:
        """读取某订单未结清的欠账。"""
        return await self._db.execute_fetchall(
            "SELECT id, order_id, mobile, member_balance_id, operation_key, amount, "
            "status, note, created_at, updated_at FROM refund_shortfall_debt "
            "WHERE order_id = ? AND status = 'open' ORDER BY id ASC",
            (order_id,),
        )


__all__ = ["RefundShortfallDebtRepo"]
