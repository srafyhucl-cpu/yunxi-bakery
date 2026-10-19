"""店员快捷开单请求幂等数据访问层。

同一 requestId 只允许一个请求占位；状态只允许 pending -> completed/failed，
completed 结果不允许被后续失败重试覆盖。
"""

from app.repository.base import BaseRepository
from app.utils import now_str

# 显式字段列表，避免 SELECT *。
_REQUEST_COLUMNS = (
    "request_id, staff_id, mode, status, order_id, error, created_at, updated_at"
)


class StaffQuickOrderRequestRepo(BaseRepository):
    """快捷开单请求占位、完成与失败标记。"""

    async def reserve(
        self,
        request_id: str,
        staff_id: str,
        mode: str,
    ) -> tuple[bool, dict | None]:
        """原子抢占 requestId，返回 (是否抢到, 既有请求行)。"""
        now = now_str()
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO staff_quick_order_requests "
            "(request_id, staff_id, mode, status, order_id, error, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, 'pending', '', '', ?, ?)",
            (request_id, staff_id, mode, now, now),
        )
        existing = await self.get(request_id)
        return bool(cursor.rowcount == 1), existing

    async def get(self, request_id: str) -> dict | None:
        """按 requestId 读取请求记录。"""
        rows = await self._db.execute_fetchall(
            "SELECT "
            + _REQUEST_COLUMNS
            + " FROM staff_quick_order_requests WHERE request_id = ? LIMIT 1",
            (request_id,),
        )
        return dict(rows[0]) if rows else None

    async def complete(self, request_id: str, order_id: str) -> bool:
        """把 pending 请求标记为 completed；已完成的请求保持原结果。"""
        cursor = await self._db.execute(
            "UPDATE staff_quick_order_requests SET status = 'completed', "
            "order_id = ?, error = '', updated_at = ? "
            "WHERE request_id = ? AND status = 'pending'",
            (order_id, now_str(), request_id),
        )
        return cursor.rowcount == 1

    async def fail(self, request_id: str, error: str) -> bool:
        """把 pending 请求标记为 failed；不覆盖已完成的请求。"""
        cursor = await self._db.execute(
            "UPDATE staff_quick_order_requests SET status = 'failed', "
            "error = ?, updated_at = ? "
            "WHERE request_id = ? AND status = 'pending'",
            (str(error or "")[:500], now_str(), request_id),
        )
        return cursor.rowcount == 1


__all__ = ["StaffQuickOrderRequestRepo"]
