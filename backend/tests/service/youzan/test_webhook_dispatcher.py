"""有赞持久 dispatcher 的重启与失败恢复测试。"""

import asyncio

import pytest

from app.api.integrations.youzan_webhook import stop_webhook_dispatchers
from app.config import settings
from app.database import close_db, db_session_scope, init_db
from app.repository.inbox_repo import InboxRepo
from app.service.youzan.webhook_dispatcher import (
    YouzanWebhookDispatcher,
    process_youzan_webhook,
)


class _ChatService:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_once = True

    async def create_youzan_webhook_audit(self, event):
        return None

    async def handle_message_and_reply_youzan(
        self, buyer_id: str, content: str, msg_id: str
    ):
        self.calls.append(msg_id)
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("send failed")


class _SlowChatService(_ChatService):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()

    async def handle_message_and_reply_youzan(
        self, buyer_id: str, content: str, msg_id: str
    ) -> None:
        self.calls.append(msg_id)
        self.started.set()
        await asyncio.sleep(0.15)


@pytest.fixture
async def webhook_db(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "dispatcher.db"))
    connection = await init_db(settings.DB_PATH)
    await close_db(connection)
    yield
    await stop_webhook_dispatchers()


@pytest.mark.asyncio
async def test_dispatcher_retries_failed_message_after_restart(webhook_db) -> None:
    service = _ChatService()
    first = YouzanWebhookDispatcher()
    payload = {
        "event_type": "",
        "msg_id": "restart-msg",
        "buyer_id": "buyer-1",
        "audit_id": None,
        "body": {"msg_type": "text", "content": {"text": "你好"}},
    }
    await first.enqueue("restart-msg", payload)
    with pytest.raises(RuntimeError, match="send failed"):
        await process_youzan_webhook(service, payload)
    async with db_session_scope():
        inbox = InboxRepo()
        await inbox.mark_failed("youzan_webhook:restart-msg", "send failed")
        await inbox._db.execute(
            "UPDATE inbox_events SET next_attempt_at = '2000-01-01 00:00:00' "
            "WHERE message_key = ?",
            ("youzan_webhook:restart-msg",),
        )
        await inbox._db.commit()

    second = YouzanWebhookDispatcher()
    second.start(service)
    await asyncio.sleep(0.6)
    await second.stop()

    assert service.calls == ["restart-msg", "restart-msg"]


@pytest.mark.asyncio
async def test_dispatcher_stop_drains_in_flight_message(webhook_db) -> None:
    service = _SlowChatService()
    dispatcher = YouzanWebhookDispatcher()
    await dispatcher.enqueue(
        "drain-msg",
        {
            "event_type": "",
            "msg_id": "drain-msg",
            "buyer_id": "buyer-1",
            "audit_id": None,
            "body": {"msg_type": "text", "content": {"text": "你好"}},
        },
    )
    dispatcher.start(service)
    await asyncio.wait_for(service.started.wait(), timeout=2)
    await dispatcher.stop()

    async with db_session_scope():
        rows = await InboxRepo()._db.execute_fetchall(
            "SELECT status FROM inbox_events WHERE message_key = ?",
            ("youzan_webhook:drain-msg",),
        )
    assert service.calls == ["drain-msg"]
    assert dict(rows[0])["status"] == "processed"
