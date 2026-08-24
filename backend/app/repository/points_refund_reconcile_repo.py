"""积分退款对账修正清单数据访问层（只追加）。"""

from app.repository.base import BaseRepository
from app.utils import now_str


class PointsRefundReconcileRepo(BaseRepository):
    """积分退款异常对账清单仓储（append-only，幂等追加）。"""

    async def append(
        self,
        *,
        order_id: str,
        mobile: str,
        unique_id: str,
        reason: str,
        amount: int,
        note: str,
        operation_key: str = "",
    ) -> bool:
        """追加一条异常记录；同订单同原因幂等，返回是否新增。

        B3.5（评审问题 3）：operation_key 为补录幂等键（默认与 unique_id 一致），
        供对账工序关联退款操作事实与欠账。
        """
        timestamp = now_str()
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO points_refund_reconcile "
            "(order_id, mobile, unique_id, reason, amount, status, note, "
            "operation_key, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)",
            (
                order_id,
                mobile,
                unique_id,
                reason,
                amount,
                note,
                operation_key or unique_id,
                timestamp,
                timestamp,
            ),
        )
        rowcount = int(cursor.rowcount or 0)
        return rowcount > 0

    async def list_open(self, *, limit: int = 100) -> list[dict]:
        """读取待处理异常记录（status='open'），按 id 升序。"""
        return await self._db.execute_fetchall(
            "SELECT id, order_id, mobile, unique_id, reason, amount, status, note, "
            "resolved_by, resolved_at, resolution, evidence_ref, operation_key, "
            "version, created_at, updated_at "
            "FROM points_refund_reconcile WHERE status = 'open' "
            "ORDER BY id ASC LIMIT ?",
            (limit,),
        )

    async def close_open(
        self,
        *,
        order_id: str,
        reason: str,
        resolved_by: str = "",
        resolution: str = "",
        evidence_ref: str = "",
    ) -> bool:
        """人工核对后关闭指定原因的对账案件（open→closed，幂等）。

        B3.4（评审问题 2）：案件必须可关闭、可审计——事实字段只追加不修改，
        仅 status 允许 open→closed 生命周期流转。
        B3.5（评审问题 3）：结案写入处理人 / 处理结论 / 证据引用，
        案件版本 version 递增（reopen 后再次结案版本继续递增，见 open_case）。
        """
        cursor = await self._db.execute(
            "UPDATE points_refund_reconcile SET status = 'closed', "
            "resolved_by = ?, resolved_at = ?, resolution = ?, evidence_ref = ?, "
            "version = version + 1, updated_at = ? "
            "WHERE order_id = ? AND reason = ? AND status = 'open'",
            (
                resolved_by,
                now_str(),
                resolution,
                evidence_ref,
                now_str(),
                order_id,
                reason,
            ),
        )
        rowcount = int(cursor.rowcount or 0)
        return rowcount > 0

    async def open_case(
        self,
        *,
        order_id: str,
        reason: str,
        note: str,
        resolved_by: str = "",
    ) -> bool:
        """已关闭案件因同一冲突复发而 reopen（closed→open，版本递增）。

        B3.5（评审问题 3）：同一订单同一原因结案后再次冲突，不允许静默重建
        事实行（会破坏 append-only），而是把案件重新打开并递增 version，
        保留历史结案审计记录。
        """
        cursor = await self._db.execute(
            "UPDATE points_refund_reconcile SET status = 'open', "
            "note = ?, resolved_by = ?, resolved_at = NULL, resolution = '', "
            "evidence_ref = '', version = version + 1, updated_at = ? "
            "WHERE order_id = ? AND reason = ? AND status = 'closed'",
            (note, resolved_by, now_str(), order_id, reason),
        )
        rowcount = int(cursor.rowcount or 0)
        return rowcount > 0


__all__ = ["PointsRefundReconcileRepo"]
