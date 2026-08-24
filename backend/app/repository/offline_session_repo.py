"""离线流水线会话候选查询。"""

from app.models.session import Session
from app.repository.base import BaseRepository


class OfflineSessionRepo(BaseRepository):
    """离线 Agent 专用会话候选仓库。"""

    async def list_memory_candidates(self, limit: int = 200) -> list[Session]:
        """获取近期可用于冷路径记忆固化的会话。"""
        rows = await self._db.execute_fetchall(
            "SELECT s.id, s.channel, s.user_id, s.staff_id, s.status, "
            "s.extra_info, s.created_at, s.updated_at FROM sessions AS s "
            "LEFT JOIN customer_profiles AS cp ON cp.channel = s.channel "
            "AND cp.user_id = s.user_id "
            "WHERE s.status IN ('closed', 'transfer_pending', 'human_service') "
            "AND (cp.id IS NULL OR cp.last_interaction_at < s.updated_at) "
            "ORDER BY s.updated_at DESC LIMIT ?",
            (limit,),
        )
        return [Session(**dict(row)) for row in rows]
