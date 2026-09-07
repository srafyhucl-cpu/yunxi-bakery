"""微信退款事件事实数据访问层。"""

from app.repository.base import BaseRepository
from app.utils import now_str


class WechatRefundEventRepo(BaseRepository):
    """微信退款事件仓储，主键幂等，只追加不修改业务字段。"""

    async def insert_event(
        self,
        *,
        out_refund_no: str,
        order_id: str,
        transaction_id: str,
        refund_id: str,
        total_fen: int,
        refund_fen: int,
        payer_refund_fen: int,
        refund_status: str,
        source: str,
    ) -> bool:
        """追加退款事件，同商户退款单号幂等，返回是否新增。"""
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO wechat_refund_events (out_refund_no, order_id, "
            "transaction_id, refund_id, total_fen, refund_fen, payer_refund_fen, "
            "refund_status, source, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                out_refund_no,
                order_id,
                transaction_id,
                refund_id,
                total_fen,
                refund_fen,
                payer_refund_fen,
                refund_status,
                source,
                now_str(),
                now_str(),
            ),
        )
        return bool(cursor.rowcount == 1)

    async def get_by_out_refund_no(self, out_refund_no: str) -> dict | None:
        """按商户退款单号读取事件。"""
        rows = await self._db.execute_fetchall(
            "SELECT out_refund_no, order_id, transaction_id, refund_id, total_fen, "
            "refund_fen, payer_refund_fen, refund_status, source, created_at, "
            "updated_at FROM wechat_refund_events WHERE out_refund_no = ? LIMIT 1",
            (out_refund_no,),
        )
        return dict(rows[0]) if rows else None

    async def sum_payer_refund_fen(self, order_id: str) -> int:
        """累计订单已记录的用户退款金额。"""
        rows = await self._db.execute_fetchall(
            "SELECT COALESCE(SUM(payer_refund_fen), 0) AS total "
            "FROM wechat_refund_events WHERE order_id = ?",
            (order_id,),
        )
        return int(rows[0]["total"]) if rows else 0
