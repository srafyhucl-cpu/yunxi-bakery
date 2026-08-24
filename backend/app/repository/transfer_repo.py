"""
转人工数据访问层。

管理转人工工单的创建、排队和状态更新。
"""

from uuid import uuid4
from datetime import datetime

from app.models.transfer import HumanTransfer, TransferStatus


from app.repository.base import BaseRepository


class TransferRepo(BaseRepository):
    """转人工仓库：创建工单、查询排队、更新状态。"""

    async def create(
        self, session_id: str, user_id: str, reason: str = "", summary: str = ""
    ) -> HumanTransfer:
        """创建转人工工单，状态初始为 pending。"""
        transfer_id = str(uuid4())
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self._db.execute(
            "INSERT INTO human_transfers "
            "(id, session_id, user_id, reason, conversation_summary, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (transfer_id, session_id, user_id, reason, summary, now),
        )
        await self._db.commit()
        return HumanTransfer(
            id=transfer_id,
            session_id=session_id,
            user_id=user_id,
            reason=reason,
            conversation_summary=summary,
            created_at=now,
        )

    async def get_pending(self) -> list[HumanTransfer]:
        """查询所有待接单的工单，按创建时间正序。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, session_id, user_id, staff_id, reason, status, "
            "conversation_summary, created_at, accepted_at, closed_at "
            "FROM human_transfers WHERE status = 'pending' ORDER BY created_at ASC",
        )
        return [HumanTransfer(**dict(r)) for r in rows]

    async def update_status(
        self, transfer_id: str, status: TransferStatus, staff_id: str = ""
    ) -> None:
        """更新工单状态，接单时记录客服 ID 和接单时间。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if status == TransferStatus.ACCEPTED:
            await self._db.execute(
                "UPDATE human_transfers SET status = ?, staff_id = ?, "
                "accepted_at = ? WHERE id = ?",
                (status.value, staff_id, now, transfer_id),
            )
        else:
            await self._db.execute(
                "UPDATE human_transfers SET status = ?, closed_at = ? WHERE id = ?",
                (status.value, now, transfer_id),
            )
        await self._db.commit()

    async def mark_latest_for_session(
        self,
        session_id: str,
        status: TransferStatus,
        staff_id: str = "",
    ) -> None:
        """按会话更新最近一条未关闭转人工工单。"""
        rows = await self._db.execute_fetchall(
            "SELECT id FROM human_transfers "
            "WHERE session_id = ? AND status IN ('pending', 'accepted') "
            "ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )
        if not rows:
            return
        await self.update_status(str(rows[0]["id"]), status, staff_id)
