"""积分流水数据访问层。"""

from app.models.member import PointsLedgerEntry
from app.repository.base import BaseRepository
from app.utils import now_str


class PointsLedgerRepo(BaseRepository):
    """积分变动流水仓储（unique_id 幂等去重）。"""

    async def get_by_unique_id(self, unique_id: str) -> dict | None:
        """按 unique_id 读取积分流水（含 biz_type / biz_id，供退款核验业务归属）。"""
        if not unique_id:
            return None
        rows = await self._db.execute_fetchall(
            "SELECT id, unique_id, customer_id, mobile, yz_open_id, amount, total, "
            "event_type, source, biz_type, biz_id, occurred_at, created_at, "
            "request_fingerprint "
            "FROM points_ledger WHERE unique_id = ? LIMIT 1",
            (unique_id,),
        )
        return dict(rows[0]) if rows else None

    async def insert(self, entry: PointsLedgerEntry) -> None:
        """写入一条积分流水。

        B3.5（评审问题 1）：账务仓储**不自提交**，由调用方统一支付应用服务 /
        摄取命令独占事务边界（流水与结算标记同一 UoW 提交，评审问题 2）。
        请求指纹随正式插入一次落库。
        """
        await self._db.execute(
            "INSERT INTO points_ledger (unique_id, customer_id, mobile, yz_open_id, "
            "amount, total, event_type, source, biz_type, biz_id, occurred_at, created_at, "
            "request_fingerprint) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.unique_id,
                entry.customer_id,
                entry.mobile,
                entry.yz_open_id,
                entry.amount,
                entry.total,
                entry.event_type,
                entry.source,
                entry.biz_type,
                entry.biz_id,
                entry.occurred_at,
                now_str(),
                entry.request_fingerprint,
            ),
        )

    async def insert_placeholder(self, entry: PointsLedgerEntry) -> bool:
        """幂等占位先行，返回是否抢到本次记账权。

        调用方须在同一事务内完成余额变更后补写余额快照；
        未抢到时调用方按已存在流水做重放校验，不得重复变更余额。
        请求指纹随占位一次落库，不存在先空后补窗口。
        """
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO points_ledger (unique_id, customer_id, mobile, "
            "yz_open_id, amount, total, event_type, source, biz_type, biz_id, "
            "occurred_at, created_at, request_fingerprint) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.unique_id,
                entry.customer_id,
                entry.mobile,
                entry.yz_open_id,
                entry.amount,
                entry.total,
                entry.event_type,
                entry.source,
                entry.biz_type,
                entry.biz_id,
                entry.occurred_at,
                now_str(),
                entry.request_fingerprint,
            ),
        )
        return bool(cursor.rowcount == 1)

    async def complete_placeholder(self, unique_id: str, total: int) -> None:
        """补写占位流水的余额快照，与余额变更同一事务提交。"""
        await self._db.execute(
            "UPDATE points_ledger SET total = ? WHERE unique_id = ?",
            (total, unique_id),
        )

    async def delete_placeholder(self, unique_id: str) -> None:
        """删除占位流水，用于余额不足等未发生变更的回退。"""
        await self._db.execute(
            "DELETE FROM points_ledger WHERE unique_id = ?",
            (unique_id,),
        )

    async def list_by_mobile(self, mobile: str, *, limit: int = 50) -> list[dict]:
        """按手机号读取积分流水，按 id 倒序。"""
        if not mobile:
            return []
        return await self._db.execute_fetchall(
            "SELECT id, unique_id, customer_id, mobile, yz_open_id, amount, total, "
            "event_type, source, biz_type, biz_id, occurred_at, created_at "
            "FROM points_ledger WHERE mobile = ? ORDER BY id DESC LIMIT ?",
            (mobile, limit),
        )
