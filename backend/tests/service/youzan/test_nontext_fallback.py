"""有赞非文本消息的幂等认领测试。"""

from app.repository.message_repo import MessageRepo
from app.repository.session_repo import SessionRepo
from app.service.chat import ChatService


class _FakeYouzanClient:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []

    async def send_reply(self, buyer_open_id: str, content: str) -> None:
        self.replies.append((buyer_open_id, content))


def _build_chat_service(db) -> tuple[ChatService, _FakeYouzanClient]:
    client = _FakeYouzanClient()
    service = ChatService.__new__(ChatService)
    service._session_repo = SessionRepo(db)
    service._message_repo = MessageRepo(db)
    service._youzan_client = client
    return service, client


async def test_nontext_fallback_claims_message_before_sending(db) -> None:
    service, client = _build_chat_service(db)

    await service.reply_youzan_nontext_fallback("buyer-1", "nontext-1")
    await service.reply_youzan_nontext_fallback("buyer-1", "nontext-1")

    assert len(client.replies) == 1
    rows = await db.execute_fetchall(
        "SELECT channel_msg_id FROM messages WHERE channel_msg_id = ?",
        ("nontext-1",),
    )
    assert [dict(row) for row in rows] == [{"channel_msg_id": "nontext-1"}]
