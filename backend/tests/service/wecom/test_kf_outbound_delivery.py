"""企微外发投递合同测试：幂等键、状态机与人工确认。"""

import pytest

from app.config import settings
from app.database import close_db, db_session_scope, init_db
from app.repository.wecom_kf_outbound_repo import (
    STATUS_FAILED,
    STATUS_SENDING,
    STATUS_SENT,
    STATUS_UNKNOWN,
    WecomKfOutboundRepo,
)
from app.service.wecom import client as wecom_client_module
from app.service.wecom.kf_message_queue import KfIncomingMessage, KfMessageQueue
from app.service.wecom.kf_outbound_sender import (
    build_outbound_key,
    request_manual_retry,
    send_text_guarded,
)


class FakeWecomClient:
    """可编排的发送客户端，记录服务端实际接收。"""

    def __init__(self, behavior: str = "success") -> None:
        self.behavior = behavior
        self.server_received: list[dict] = []
        self.send_calls: list[dict] = []

    async def get_token(self) -> str:
        return "token"

    async def send_kf_text(
        self, external_userid: str, content: str, msgid: str = ""
    ) -> dict:
        call = {"touser": external_userid, "content": content, "msgid": msgid}
        self.send_calls.append(call)
        if self.behavior == "timeout":
            raise TimeoutError("模拟供应商超时")
        if self.behavior == "timeout_after_receipt":
            self.server_received.append(call)
            raise TimeoutError("模拟响应丢失")
        if self.behavior == "api_error":
            return {"errcode": 40001, "errmsg": "模拟拒绝"}
        self.server_received.append(call)
        return {"errcode": 0, "errmsg": "ok"}

    async def send_kf_link(self, **kwargs) -> dict:
        return {"errcode": 0, "errmsg": "ok"}

    async def ensure_kf_session_active(self, external_userid: str) -> bool:
        return True

    async def get_kf_service_state(self, external_userid: str):
        return None


class FakeChatService:
    """固定回复的对话服务。"""

    def __init__(self, reply: str = "自动回复") -> None:
        self.reply = reply

    async def handle_message(self, **kwargs) -> str:
        return self.reply


@pytest.fixture
async def outbound_db(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """每个用例独享文件数据库。"""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "kf-outbound.db"))
    connection = await init_db(settings.DB_PATH)
    await close_db(connection)
    yield


@pytest.mark.asyncio
async def test_success_sends_once_with_stable_msgid(outbound_db) -> None:
    """成功发送一次并持久化供应商消息标识，重复消费不再发送。"""
    client = FakeWecomClient("success")
    status = await send_text_guarded(client, "user-1", "in-msg-1", "你好")
    assert status == STATUS_SENT
    assert client.server_received[0]["msgid"] == build_outbound_key("in-msg-1")
    assert len(client.send_calls) == 1

    status = await send_text_guarded(client, "user-1", "in-msg-1", "你好")
    assert status == STATUS_SENT
    assert len(client.send_calls) == 1
    assert len(client.server_received) == 1


@pytest.mark.asyncio
async def test_timeout_becomes_unknown_without_resend(outbound_db) -> None:
    """超时转未知态，重复消费不重发，需人工确认。"""
    client = FakeWecomClient("timeout")
    assert (
        await send_text_guarded(client, "user-1", "in-msg-2", "你好") == STATUS_UNKNOWN
    )
    assert client.server_received == []

    assert (
        await send_text_guarded(client, "user-1", "in-msg-2", "你好") == STATUS_UNKNOWN
    )
    assert len(client.send_calls) == 1

    async with db_session_scope():
        row = await WecomKfOutboundRepo().get(build_outbound_key("in-msg-2"))
    assert row is not None
    assert row["status"] == STATUS_UNKNOWN


@pytest.mark.asyncio
async def test_response_loss_sends_only_once(outbound_db) -> None:
    """响应丢失时服务端只收到一次，本地未知态不自动补发。"""
    client = FakeWecomClient("timeout_after_receipt")
    assert (
        await send_text_guarded(client, "user-1", "in-msg-3", "你好") == STATUS_UNKNOWN
    )
    assert len(client.server_received) == 1

    assert (
        await send_text_guarded(client, "user-1", "in-msg-3", "你好") == STATUS_UNKNOWN
    )
    assert len(client.server_received) == 1


@pytest.mark.asyncio
async def test_api_error_becomes_failed_without_resend(outbound_db) -> None:
    """供应商明确拒绝记失败态，不自动重发。"""
    client = FakeWecomClient("api_error")
    assert (
        await send_text_guarded(client, "user-1", "in-msg-4", "你好") == STATUS_FAILED
    )
    assert (
        await send_text_guarded(client, "user-1", "in-msg-4", "你好") == STATUS_FAILED
    )
    assert len(client.send_calls) == 1


@pytest.mark.asyncio
async def test_crash_during_sending_backs_off_then_takeover(outbound_db) -> None:
    """发送中崩溃后先退避不覆盖，租约过期后接管只发送一次。"""
    client = FakeWecomClient("success")
    key = build_outbound_key("in-msg-5")
    async with db_session_scope():
        repo = WecomKfOutboundRepo()
        _row, can_send = await repo.claim_for_send(
            key, "kf-1", "user-1", "in-msg-5", "text"
        )
        assert can_send is True

    # 租约有效：重复消费退避，不发送不改状态。
    assert (
        await send_text_guarded(client, "user-1", "in-msg-5", "你好") == STATUS_SENDING
    )
    assert len(client.send_calls) == 0
    async with db_session_scope():
        row = await WecomKfOutboundRepo().get(key)
    assert row is not None
    assert row["status"] == STATUS_SENDING

    # 租约过期：新认领接管并发送一次，旧凭证失效。
    async with db_session_scope():
        repo = WecomKfOutboundRepo()
        await repo._db.execute(
            "UPDATE wecom_kf_outbound_ledger SET updated_at = datetime('now', '-600 seconds') "
            "WHERE outbound_key = ?",
            (key,),
        )
    assert await send_text_guarded(client, "user-1", "in-msg-5", "你好") == STATUS_SENT
    assert len(client.send_calls) == 1
    async with db_session_scope():
        row = await WecomKfOutboundRepo().get(key)
    assert row is not None
    assert row["status"] == STATUS_SENT


@pytest.mark.asyncio
async def test_manual_retry_requeues_and_resends(outbound_db) -> None:
    """人工确认后可重新排队并发送成功。"""
    client = FakeWecomClient("timeout")
    assert (
        await send_text_guarded(client, "user-1", "in-msg-6", "你好") == STATUS_UNKNOWN
    )

    assert (
        await request_manual_retry(
            build_outbound_key("in-msg-6"), "operator-1", "已与供应商核对未送达"
        )
        is True
    )

    client.behavior = "success"
    assert await send_text_guarded(client, "user-1", "in-msg-6", "你好") == STATUS_SENT
    assert len(client.server_received) == 1

    async with db_session_scope():
        row = await WecomKfOutboundRepo().get(build_outbound_key("in-msg-6"))
    assert row is not None
    assert row["status"] == STATUS_SENT
    assert row["attempt_count"] == 2


@pytest.mark.asyncio
async def test_manual_retry_rejects_sent_and_pending(outbound_db) -> None:
    """已发送与待发送记录不可被人工重试重复排队。"""
    client = FakeWecomClient("success")
    await send_text_guarded(client, "user-1", "in-msg-7", "你好")
    assert (
        await request_manual_retry(build_outbound_key("in-msg-7"), "op", "误操作")
        is False
    )
    assert (
        await request_manual_retry("wecom_kf:out:missing:part", "op", "误操作") is False
    )


@pytest.mark.asyncio
async def test_worker_duplicate_consumption_sends_once(
    outbound_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """队列重复消费同一消息时供应商只收到一次回复。"""
    client = FakeWecomClient("success")
    monkeypatch.setattr(wecom_client_module, "get_wecom_client", lambda: client)
    queue = KfMessageQueue()
    queue._chat_service = FakeChatService()  # noqa: SLF001
    msg = KfIncomingMessage(
        external_userid="user-1", open_kfid="kf-1", content="你好", msg_id="dup-out-1"
    )
    await queue._process_one(msg)  # noqa: SLF001
    await queue._process_one(msg)  # noqa: SLF001
    assert len(client.server_received) == 1
    async with db_session_scope():
        row = await WecomKfOutboundRepo().get(build_outbound_key("dup-out-1"))
    assert row is not None
    assert row["status"] == STATUS_SENT
