"""券冲突对账案件数据访问层（只追加，幂等）。"""

from app.repository.base import BaseRepository
from app.utils import now_str


class CouponReconcileRepo(BaseRepository):
    """券核销冲突对账案件仓储（append-only，case_key 幂等追加）。"""

    async def append(
        self,
        *,
        case_key: str,
        coupon_id: str,
        mobile: str,
        order_id: str,
        reason: str,
        deducted_fen: int,
        external_order_no: str = "",
        external_source: str = "",
        note: str = "",
    ) -> bool:
        """追加一条券冲突案件；同 case_key 幂等，返回是否新增。

        支付腿与退款腿共用同一 case_key：同一订单同一张券的外部核销冲突
        只留一条案件，退款重入不会重复开案。
        """
        timestamp = now_str()
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO coupon_reconcile_case "
            "(case_key, coupon_id, mobile, order_id, external_order_no, "
            "external_source, reason, deducted_fen, status, note, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)",
            (
                case_key,
                coupon_id,
                mobile,
                order_id,
                external_order_no,
                external_source,
                reason,
                max(0, int(deducted_fen or 0)),
                note,
                timestamp,
                timestamp,
            ),
        )
        return int(cursor.rowcount or 0) > 0

    async def list_by_order(self, order_id: str) -> list[dict]:
        """读取指定订单的券对账案件（按 id 升序）。"""
        return await self._db.execute_fetchall(
            "SELECT id, case_key, coupon_id, mobile, order_id, external_order_no, "
            "external_source, reason, deducted_fen, status, note, "
            "created_at, updated_at FROM coupon_reconcile_case "
            "WHERE order_id = ? ORDER BY id ASC",
            (order_id,),
        )


__all__ = ["CouponReconcileRepo"]
