"""P0-6 同步租约与 P1-1 外发投递补充测试。

P0-6：并发回调互斥、租约过期接管、拉取失败释放租约、分页截断延续、
陈旧凭证拒绝。
P1-1：同键异内容冲突、传输异常转未知不重发、人工重排、欢迎语入账本。
"""

import pytest

from app.config import settings
from app.database import close_db, db_session_scope, init_db
from app.repository.wecom_kf_sync_lease_repo import WecomKfSyncLeaseRepo
from app.repository.wecom_kf_sync_repo import WecomKfSyncRepo
from app.repository.wecom_kf_outbound_repo import WecomKfOutboundRepo
from app.service.wecom import kf_callback_processor as processor_module
from app.service.wecom.kf_callback_processor import KfCallbackProcessor
from app.service.wecom.kf_message_queue import KfIncomingMessage
from app.service.wecom.kf_outbound_sender import (
    build_outbound_key,
    request_manual_retry,
    send_event_guarded,
    send_text_guarded,
)


@pytest.fixture
async def lease_db(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """每个用例独享文件数据库。"""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "kf-lease.db"))
    connection = await init_db(settings.DB_PATH)
    await close_db(connection)
    yield


class FakeKfClient:
    """最小同步与发送客户端。"""

    def __init__(self, pages: list[dict]) -> None:
        self.pages = pages
        self.calls = 0
        self.event_texts: list[tuple[str, str, str]] = []
        self.texts: list[tuple[str, str, str]] = []

    async def sync_kf_messages(self, kf_token: str, cursor: str = "") -> dict:
        index = min(self.calls, len(self.pages) - 1)
        self.calls += 1
        return self.pages[index]

    async def ensure_kf_session_active(self, external_userid: str) -> bool:
        return True

    async def get_kf_service_state(self, external_userid: str):
        return None

    async def send_kf_event_text(
        self, code: str, content: str, msgid: str = ""
    ) -> dict:
        self.event_texts.append((code, content, msgid))
        return {"errcode": 0}

    async def send_kf_text(
        self, external_userid: str, content: str, msgid: str = ""
    ) -> dict:
        self.texts.append((external_userid, content, msgid))
        return {"errcode": 0}


class FakeKfQueue:
    """内存通知队列。"""

    def __init__(self) -> None:
        self.messages: list[KfIncomingMessage] = []

    async def enqueue(self, msg: KfIncomingMessage) -> bool:
        self.messages.append(msg)
        return True


def _text_page(msg_id: str, cursor: str, has_more: int = 0) -> dict:
    """构造单条文本分页。"""
    return {
        "errcode": 0,
        "has_more": has_more,
        "next_cursor": cursor,
        "msg_list": [
            {
                "origin": 3,
                "msgtype": "text",
                "msgid": msg_id,
                "external_userid": "user-1",
                "text": {"content": "你好"},
            }
        ],
    }


@pytest.mark.asyncio
async def test_concurrent_callback_single_syncer(lease_db) -> None:
    """P0-6：租约被持有时并发回调不得成为同步者，且不推进游标。"""
    async with db_session_scope() as db:
        held = await WecomKfSyncLeaseRepo(db).acquire("kf-conc", lease_seconds=300)
    assert held is not None
    processor = KfCallbackProcessor(
        FakeKfClient([_text_page("conc-1", "cursor-conc")]), FakeKfQueue()
    )
    await processor.handle_callback({"Token": "t", "OpenKfId": "kf-conc"})
    async with db_session_scope() as db:
        state = await WecomKfSyncRepo(db).get_state("kf-conc")
        assert state.last_cursor == ""
        ledger = await db.execute_fetchall(
            "SELECT msg_id FROM wecom_kf_message_ledger WHERE msg_id = ?",
            ("conc-1",),
        )
        assert ledger == []
    async with db_session_scope() as db:
        released = await WecomKfSyncLeaseRepo(db).complete(
            "kf-conc", str(held["lease_token"])
        )
        assert released is True
    queue = FakeKfQueue()
    await KfCallbackProcessor(
        FakeKfClient([_text_page("conc-1", "cursor-conc")]), queue
    ).handle_callback({"Token": "t", "OpenKfId": "kf-conc"})
    assert [msg.msg_id for msg in queue.messages] == ["conc-1"]


@pytest.mark.asyncio
async def test_expired_lease_takeover(lease_db) -> None:
    """P0-6：租约过期后新回调可接管，进程重启不丢消息。"""
    async with db_session_scope() as db:
        expired = await WecomKfSyncLeaseRepo(db).acquire("kf-exp", lease_seconds=-1)
    assert expired is not None
    queue = FakeKfQueue()
    await KfCallbackProcessor(
        FakeKfClient([_text_page("exp-1", "cursor-exp")]), queue
    ).handle_callback({"Token": "t", "OpenKfId": "kf-exp"})
    assert [msg.msg_id for msg in queue.messages] == ["exp-1"]
    async with db_session_scope() as db:
        state = await WecomKfSyncRepo(db).get_state("kf-exp")
        assert state.last_cursor == "cursor-exp"


@pytest.mark.asyncio
async def test_pull_failure_releases_lease(lease_db) -> None:
    """P0-6：拉取失败只记失败不推进游标，并释放租约供下次同步。"""
    failing = FakeKfClient([{"errcode": 1001, "errmsg": "限流"}])
    await KfCallbackProcessor(failing, FakeKfQueue()).handle_callback(
        {"Token": "t", "OpenKfId": "kf-fail"}
    )
    async with db_session_scope() as db:
        state = await WecomKfSyncRepo(db).get_state("kf-fail")
        assert state.last_cursor == ""
        assert state.status == "failed"
        lease = await WecomKfSyncLeaseRepo(db).get("kf-fail")
        assert lease is not None and str(lease["lease_token"]) == ""
    queue = FakeKfQueue()
    await KfCallbackProcessor(
        FakeKfClient([_text_page("fail-1", "cursor-fail")]), queue
    ).handle_callback({"Token": "t", "OpenKfId": "kf-fail"})
    assert [msg.msg_id for msg in queue.messages] == ["fail-1"]


@pytest.mark.asyncio
async def test_truncation_records_continuation(
    lease_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0-6：达到分页上限不静默推进，保存延续状态供后续同步。"""
    monkeypatch.setattr(processor_module, "MAX_SYNC_PAGES", 1)
    pages = [
        _text_page("trunc-1", "cursor-t1", has_more=1),
        _text_page("trunc-2", "cursor-t2"),
    ]
    queue = FakeKfQueue()
    await KfCallbackProcessor(FakeKfClient(pages), queue).handle_callback(
        {"Token": "t", "OpenKfId": "kf-trunc"}
    )
    assert [msg.msg_id for msg in queue.messages] == ["trunc-1"]
    async with db_session_scope() as db:
        state = await WecomKfSyncRepo(db).get_state("kf-trunc")
        assert state.last_cursor == "cursor-t1"
        lease = await WecomKfSyncLeaseRepo(db).get("kf-trunc")
        assert lease is not None
        assert int(lease["has_more"]) == 1
        assert str(lease["continuation_cursor"]) == "cursor-t1"


@pytest.mark.asyncio
async def test_stale_lease_token_rejected(lease_db) -> None:
    """P0-6：陈旧同步者的租约凭证不得提交，返回假。"""
    async with db_session_scope() as db:
        first = await WecomKfSyncLeaseRepo(db).acquire("kf-stale", lease_seconds=-1)
        assert first is not None
        second = await WecomKfSyncLeaseRepo(db).acquire("kf-stale", lease_seconds=300)
        assert second is not None
        assert await WecomKfSyncLeaseRepo(db).complete("kf-stale", "过期凭证") is False
        assert (
            await WecomKfSyncLeaseRepo(db).complete(
                "kf-stale", str(second["lease_token"])
            )
            is True
        )


@pytest.mark.asyncio
async def test_outbound_same_key_different_content_conflict(lease_db) -> None:
    """P1-1：同一投递键不同内容必须冲突，禁止覆盖。"""
    client = FakeKfClient([])
    assert await send_text_guarded(client, "user-1", "in-hash-1", "原内容") == "sent"
    with pytest.raises(ValueError, match="外发内容冲突"):
        await send_text_guarded(client, "user-1", "in-hash-1", "篡改内容")
    assert len(client.texts) == 1


@pytest.mark.asyncio
async def test_outbound_transport_unknown_no_resend(lease_db) -> None:
    """P1-1：传输异常转未知态，不自动重发，人工确认后可重排。"""
    from unittest.mock import AsyncMock

    client = FakeKfClient([])
    client.send_kf_text = AsyncMock(side_effect=TimeoutError("响应丢失"))
    assert await send_text_guarded(client, "user-1", "in-unk-1", "你好") == "unknown"
    assert await send_text_guarded(client, "user-1", "in-unk-1", "你好") == "unknown"
    assert client.send_kf_text.await_count == 1
    key = build_outbound_key("in-unk-1", "text")
    assert await request_manual_retry(key, "op-1", "人工已确认未送达") is True
    async with db_session_scope():
        row = await WecomKfOutboundRepo().get(key)
        assert row is not None and row["status"] == "pending"


@pytest.mark.asyncio
async def test_welcome_event_goes_through_ledger(lease_db) -> None:
    """P1-1：欢迎语统一经过投递账本，重复事件不重复发送。"""
    client = FakeKfClient([])
    first = await send_event_guarded(client, "code-w", "in-ev-1", "欢迎语")
    second = await send_event_guarded(client, "code-w", "in-ev-1", "欢迎语")
    assert (first, second) == ("sent", "sent")
    assert len(client.event_texts) == 1
    key = build_outbound_key("in-ev-1", "welcome")
    async with db_session_scope():
        row = await WecomKfOutboundRepo().get(key)
        assert row is not None and row["status"] == "sent"
