"""客户会话短期摘要数据访问层。"""

from uuid import uuid4

from app.models.conversation_summary import (
    ConversationSummary,
    ConversationSummaryCreate,
    ConversationSummaryStatus,
)
from app.repository.base import BaseRepository
from app.utils import now_str


class ConversationSummaryRepo(BaseRepository):
    """会话摘要仓库：维护每个会话最多一条 active 摘要。"""

    async def get_active(self, session_id: str) -> ConversationSummary | None:
        rows = await self._db.execute_fetchall(
            "SELECT id, session_id, channel, user_id, summary_text, state_json, "
            "source_message_ids_json, source_until_message_id, token_estimate, "
            "status, created_at, updated_at "
            "FROM conversation_summaries "
            "WHERE session_id = ? AND status = ? "
            "ORDER BY updated_at DESC, created_at DESC LIMIT 1",
            (session_id, ConversationSummaryStatus.ACTIVE.value),
        )
        return ConversationSummary(**rows[0]) if rows else None

    async def upsert_active(
        self,
        summary: ConversationSummaryCreate,
    ) -> ConversationSummary:
        now = now_str()
        await self._db.execute(
            "UPDATE conversation_summaries SET status = ?, updated_at = ? "
            "WHERE session_id = ? AND status = ?",
            (
                ConversationSummaryStatus.SUPERSEDED.value,
                now,
                summary.session_id,
                ConversationSummaryStatus.ACTIVE.value,
            ),
        )
        summary_id = str(uuid4())
        await self._db.execute(
            "INSERT INTO conversation_summaries ("
            "id, session_id, channel, user_id, summary_text, state_json, "
            "source_message_ids_json, source_until_message_id, token_estimate, "
            "status, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                summary_id,
                summary.session_id,
                summary.channel,
                summary.user_id,
                summary.summary_text,
                summary.state_json,
                summary.source_message_ids_json,
                summary.source_until_message_id,
                summary.token_estimate,
                ConversationSummaryStatus.ACTIVE.value,
                now,
                now,
            ),
        )
        await self._db.commit()
        saved = await self.get_active(summary.session_id)
        if saved is None:
            raise RuntimeError("会话摘要写入后未能读回")
        return saved

    async def discard_active(self, session_id: str) -> int:
        now = now_str()
        cursor = await self._db.execute(
            "UPDATE conversation_summaries SET status = ?, updated_at = ? "
            "WHERE session_id = ? AND status = ?",
            (
                ConversationSummaryStatus.DISCARDED.value,
                now,
                session_id,
                ConversationSummaryStatus.ACTIVE.value,
            ),
        )
        await self._db.commit()
        return int(cursor.rowcount or 0)

    async def list_by_session(self, session_id: str) -> list[ConversationSummary]:
        rows = await self._db.execute_fetchall(
            "SELECT id, session_id, channel, user_id, summary_text, state_json, "
            "source_message_ids_json, source_until_message_id, token_estimate, "
            "status, created_at, updated_at "
            "FROM conversation_summaries WHERE session_id = ? "
            "ORDER BY created_at DESC, id DESC",
            (session_id,),
        )
        return [ConversationSummary(**row) for row in rows]
