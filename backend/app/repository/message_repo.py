"""
消息数据访问层。

按会话查询消息（用于 LLM 上下文构建）、按 channel_msg_id 去重。
"""

from uuid import uuid4
from datetime import datetime

from app.models.message import Message
from app.repository.base import BaseRepository

MAX_MESSAGES_PER_SESSION = 50


class MessageRepo(BaseRepository):
    """消息仓库：保存、去重检查、按会话查询。"""

    async def exists(self, channel_msg_id: str) -> bool:
        """根据渠道原始消息 ID 检查是否已处理（幂等去重）。"""
        if not channel_msg_id:
            return False
        row = await self._db.execute_fetchall(
            "SELECT 1 FROM messages WHERE channel_msg_id = ? LIMIT 1",
            (channel_msg_id,),
        )
        return bool(row)

    async def has_processed(self, channel_msg_id: str) -> bool:
        """检查渠道原始消息 ID 是否已经处理（别名，用于 Webhook 秒回防御）。"""
        return await self.exists(channel_msg_id)

    async def save(self, message: Message) -> None:
        """保存一条消息到数据库。"""
        await self._insert(message)
        await self._db.commit()

    async def save_if_new(self, message: Message) -> bool:
        """以数据库原子语义认领并保存渠道消息。"""
        if not message.channel_msg_id:
            await self._insert(message)
            return True

        msg_id = message.id or str(uuid4())
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        transaction_was_active = bool(getattr(self._db, "in_transaction", False))
        cursor = await self._db.execute(
            "INSERT INTO messages "
            "(id, session_id, role, content, channel_msg_id, "
            " estimated_tokens, tool_calls, tool_name, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(channel_msg_id) WHERE channel_msg_id <> '' DO NOTHING",
            (
                msg_id,
                message.session_id,
                message.role.value,
                message.content,
                message.channel_msg_id,
                message.estimated_tokens,
                message.tool_calls,
                message.tool_name,
                now,
            ),
        )
        if not transaction_was_active:
            await self._db.commit()
        return bool(cursor.rowcount == 1)

    async def _insert(self, message: Message) -> None:
        """执行消息插入，不改变调用方事务边界。"""
        msg_id = message.id or str(uuid4())
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self._db.execute(
            "INSERT INTO messages "
            "(id, session_id, role, content, channel_msg_id, "
            " estimated_tokens, tool_calls, tool_name, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                msg_id,
                message.session_id,
                message.role.value,
                message.content,
                message.channel_msg_id,
                message.estimated_tokens,
                message.tool_calls,
                message.tool_name,
                now,
            ),
        )

    async def get_by_session(
        self, session_id: str, limit: int = MAX_MESSAGES_PER_SESSION
    ) -> list[Message]:
        """查询某会话最近 limit 条消息，按时间正序返回。

        先按 created_at 倒序截取最近 N 条，再正序返回，避免会话超过 limit 时
        只取到最旧的消息而丢失最新上下文（N-1：取旧丢新）。rowid 作为同秒内的
        稳定排序兜底。
        """
        rows = await self._db.execute_fetchall(
            "SELECT id, session_id, role, content, channel_msg_id, "
            "estimated_tokens, tool_calls, tool_name, created_at "
            "FROM messages WHERE session_id = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (session_id, limit),
        )
        return [Message(**dict(r)) for r in reversed(rows)]
