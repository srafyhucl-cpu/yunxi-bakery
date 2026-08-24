"""知识缺口建议数据访问层。"""

from app.models.knowledge_gap import (
    KnowledgeGap,
    KnowledgeGapCreate,
    KnowledgeGapStatus,
)
from app.repository.base import BaseRepository
from app.repository.knowledge_gap_upsert import upsert_open_gap
from app.utils import now_str


class KnowledgeGapRepo(BaseRepository):
    """知识缺口仓库：写入建议、按状态查询与更新处理状态。"""

    async def create(self, gap: KnowledgeGapCreate) -> KnowledgeGap:
        now = now_str()
        await self._db.execute(
            "INSERT INTO knowledge_gaps ("
            "question_norm, frequency, status, proposed_answer, "
            "related_sessions_json, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                gap.question_norm,
                gap.frequency,
                gap.status,
                gap.proposed_answer,
                gap.related_sessions_json,
                now,
                now,
            ),
        )
        await self._db.commit()
        rows = await self._db.execute_fetchall("SELECT last_insert_rowid() AS id")
        return KnowledgeGap(
            id=int(rows[0]["id"]),
            question_norm=gap.question_norm,
            frequency=gap.frequency,
            status=gap.status,
            proposed_answer=gap.proposed_answer,
            related_sessions_json=gap.related_sessions_json,
            created_at=now,
            updated_at=now,
        )

    async def upsert_open(self, gap: KnowledgeGapCreate) -> KnowledgeGap:
        """按归一化问题累加 open 缺口频次。"""
        return await upsert_open_gap(self._db, gap)

    async def list_by_status(
        self,
        status: str,
        limit: int = 50,
    ) -> list[KnowledgeGap]:
        rows = await self._db.execute_fetchall(
            "SELECT id, question_norm, frequency, status, proposed_answer, "
            "related_sessions_json, created_at, updated_at "
            "FROM knowledge_gaps WHERE status = ? "
            "ORDER BY frequency DESC, updated_at DESC LIMIT ?",
            (status, limit),
        )
        return [KnowledgeGap(**dict(row)) for row in rows]

    async def list_open_top(self, limit: int = 50) -> list[KnowledgeGap]:
        return await self.list_by_status(KnowledgeGapStatus.OPEN.value, limit)

    async def update_status(
        self,
        gap_id: int,
        status: str,
        proposed_answer: str | None = None,
    ) -> None:
        now = now_str()
        await self._db.execute(
            "UPDATE knowledge_gaps SET status = ?, "
            "proposed_answer = COALESCE(?, proposed_answer), updated_at = ? "
            "WHERE id = ?",
            (status, proposed_answer, now, gap_id),
        )
        await self._db.commit()
