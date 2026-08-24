"""离线会话质检数据访问层。"""

from app.models.conversation_review import (
    ConversationReview,
    ConversationReviewCreate,
)
from app.repository.base import BaseRepository
from app.utils import now_str


class ConversationReviewRepo(BaseRepository):
    """会话质检仓库：写入质检结果并按会话或分数查询。"""

    async def create(self, review: ConversationReviewCreate) -> ConversationReview:
        reviewed_at = review.reviewed_at or now_str()
        await self._db.execute(
            "INSERT INTO conversation_reviews ("
            "session_id, quality_score, issues_json, reviewer_model, reviewed_at"
            ") VALUES (?, ?, ?, ?, ?)",
            (
                review.session_id,
                review.quality_score,
                review.issues_json,
                review.reviewer_model,
                reviewed_at,
            ),
        )
        await self._db.commit()
        rows = await self._db.execute_fetchall("SELECT last_insert_rowid() AS id")
        return ConversationReview(
            id=int(rows[0]["id"]),
            session_id=review.session_id,
            quality_score=review.quality_score,
            issues_json=review.issues_json,
            reviewer_model=review.reviewer_model,
            reviewed_at=reviewed_at,
        )

    async def list_by_session(self, session_id: str) -> list[ConversationReview]:
        rows = await self._db.execute_fetchall(
            "SELECT id, session_id, quality_score, issues_json, reviewer_model, reviewed_at "
            "FROM conversation_reviews WHERE session_id = ? "
            "ORDER BY reviewed_at DESC, id DESC",
            (session_id,),
        )
        return [ConversationReview(**dict(row)) for row in rows]

    async def list_low_score(
        self,
        max_score: int,
        limit: int = 50,
    ) -> list[ConversationReview]:
        rows = await self._db.execute_fetchall(
            "SELECT id, session_id, quality_score, issues_json, reviewer_model, reviewed_at "
            "FROM conversation_reviews WHERE quality_score <= ? "
            "ORDER BY quality_score ASC, reviewed_at DESC LIMIT ?",
            (max_score, limit),
        )
        return [ConversationReview(**dict(row)) for row in rows]
