"""储值充值单数据访问层。"""

from app.models.stored_value import RechargeOrder, RechargeStatus
from app.repository.base import BaseRepository
from app.utils import now_str


class RechargeRepo(BaseRepository):
    """充值单仓储（原子状态流转，防止重复入账）。"""

    RECHARGE_COLUMNS = (
        "id, user_id, mobile, amount_fen, status, payment_method, paid_at, "
        "expired_at, created_at, updated_at"
    )

    async def create(self, recharge: RechargeOrder) -> None:
        """创建充值单。

        B3.5（评审问题 1）：账务仓储**不自提交**，由调用方服务事务边界提交
        （RechargeService 外层 transaction 或 db_session_scope）。
        """
        await self._db.execute(
            "INSERT INTO stored_value_recharge (id, user_id, mobile, amount_fen, "
            "status, payment_method, paid_at, expired_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                recharge.id,
                recharge.user_id,
                recharge.mobile,
                recharge.amount_fen,
                recharge.status,
                recharge.payment_method,
                recharge.paid_at,
                recharge.expired_at,
                recharge.created_at,
                recharge.updated_at,
            ),
        )

    async def get(self, recharge_id: str) -> RechargeOrder | None:
        """按充值单号读取充值单。"""
        rows = await self._db.execute_fetchall(
            "SELECT "
            + self.RECHARGE_COLUMNS
            + " FROM stored_value_recharge WHERE id = ? LIMIT 1",
            (recharge_id,),
        )
        return RechargeOrder(**dict(rows[0])) if rows else None

    async def list_by_user(
        self, user_id: str, *, limit: int = 50
    ) -> list[RechargeOrder]:
        """按用户读取充值单列表。"""
        rows = await self._db.execute_fetchall(
            "SELECT "
            + self.RECHARGE_COLUMNS
            + " FROM stored_value_recharge WHERE user_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        return [RechargeOrder(**dict(row)) for row in rows]

    async def mark_paid_if_unpaid(
        self,
        recharge_id: str,
        *,
        payment_method: str,
        paid_at: str,
    ) -> RechargeOrder | None:
        """原子认领未支付充值单为已支付，防止重复入账。"""
        cursor = await self._db.execute(
            "UPDATE stored_value_recharge SET status = ?, payment_method = ?, "
            "paid_at = ?, updated_at = ? WHERE id = ? AND status = ?",
            (
                RechargeStatus.PAID,
                payment_method,
                paid_at,
                now_str(),
                recharge_id,
                RechargeStatus.UNPAID,
            ),
        )
        if cursor.rowcount != 1:
            return None
        return await self.get(recharge_id)

    async def cancel_if_unpaid(self, recharge_id: str) -> RechargeOrder | None:
        """原子取消未支付充值单。"""
        cursor = await self._db.execute(
            "UPDATE stored_value_recharge SET status = ?, updated_at = ? "
            "WHERE id = ? AND status = ?",
            (
                RechargeStatus.CANCELLED,
                now_str(),
                recharge_id,
                RechargeStatus.UNPAID,
            ),
        )
        if cursor.rowcount != 1:
            return None
        return await self.get(recharge_id)

    async def expire_if_unpaid(
        self,
        recharge_id: str,
        *,
        expired_at: str,
    ) -> RechargeOrder | None:
        """原子关闭超时未支付充值单。"""
        cursor = await self._db.execute(
            "UPDATE stored_value_recharge SET status = ?, expired_at = ?, "
            "updated_at = ? WHERE id = ? AND status = ?",
            (
                RechargeStatus.EXPIRED,
                expired_at,
                now_str(),
                recharge_id,
                RechargeStatus.UNPAID,
            ),
        )
        if cursor.rowcount != 1:
            return None
        return await self.get(recharge_id)
