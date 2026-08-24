import time
from datetime import datetime

import pytest

from app.database import close_db, init_db
from app.models.session import SessionStatus
from app.models.session_scope import SessionScope
from app.models.transfer import TransferStatus
from app.service.wecom.kf_callback_processor import KfCallbackProcessor
from app.service.wecom.kf_message_queue import KfIncomingMessage
from app.service.wecom.kf_message_queue import KfMessageQueue


class FakeKfClient:
    def __init__(
        self,
        sync_result: dict | list[dict],
        inactive_users: set[str] | None = None,
        service_states: dict[str, int | None] | None = None,
    ) -> None:
        self.sync_results = (
            sync_result if isinstance(sync_result, list) else [sync_result]
        )
        self.inactive_users = inactive_users or set()
        self.checked_users: list[str] = []
        self.cursors: list[str] = []
        self.event_texts: list[tuple[str, str, str]] = []
        self.service_states = service_states or {}
        self.service_state_checks: list[str] = []

    async def sync_kf_messages(self, kf_token: str, cursor: str = "") -> dict:
        assert kf_token == "token-1"
        self.cursors.append(cursor)
        index = min(len(self.cursors) - 1, len(self.sync_results) - 1)
        return self.sync_results[index]

    async def ensure_kf_session_active(self, external_userid: str) -> bool:
        self.checked_users.append(external_userid)
        return external_userid not in self.inactive_users

    async def get_kf_service_state(self, external_userid: str) -> int | None:
        self.service_state_checks.append(external_userid)
        return self.service_states.get(external_userid)

    async def send_kf_event_text(
        self, code: str, content: str, msgid: str = ""
    ) -> dict:
        self.event_texts.append((code, content, msgid))
        return {"errcode": 0}


class FakeKfQueue:
    def __init__(self) -> None:
        self.messages: list[KfIncomingMessage] = []

    async def enqueue(self, msg: KfIncomingMessage) -> bool:
        self.messages.append(msg)
        return True


class FakeChatService:
    def __init__(self, reply: str = "自动回复") -> None:
        self.reply = reply
        self.calls: list[dict] = []

    async def handle_message(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return self.reply


class _FixedDatetime(datetime):
    @classmethod
    def now(cls) -> datetime:
        return cls(2026, 6, 10, 13, 1, 0)


async def prepare_kf_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    db_path = tmp_path / "kf-sync.db"
    monkeypatch.setattr("app.database.settings.DB_PATH", str(db_path))
    monkeypatch.setattr(
        "app.service.wecom.kf_handoff_checker.settings.WECOM_KF_SESSION_IDLE_CLOSE_SECONDS",
        24 * 60 * 60,
    )
    db = await init_db(str(db_path))
    await close_db(db)
    return str(db_path)


@pytest.mark.asyncio
async def test_processor_filters_stale_and_duplicate_messages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    await prepare_kf_db(tmp_path, monkeypatch)
    now = int(time.time())
    monkeypatch.setattr(time, "time", lambda: now)
    sync_result = {
        "errcode": 0,
        "msg_list": [
            {
                "origin": 3,
                "msgtype": "text",
                "msgid": "fresh-text",
                "external_userid": "user-1",
                "send_time": now,
                "text": {"content": "想订生日蛋糕"},
            },
            {
                "origin": 3,
                "msgtype": "text",
                "msgid": "fresh-text",
                "external_userid": "user-1",
                "send_time": now,
                "text": {"content": "重复消息"},
            },
            {
                "origin": 3,
                "msgtype": "text",
                "msgid": "stale-text",
                "external_userid": "user-1",
                "send_time": now - 121,
                "text": {"content": "历史消息"},
            },
            {
                "origin": 3,
                "msgtype": "image",
                "msgid": "image-1",
                "external_userid": "user-1",
                "send_time": now,
                "image": {"media_id": "media-1"},
            },
            {
                "origin": 3,
                "msgtype": "voice",
                "msgid": "voice-1",
                "external_userid": "user-1",
                "send_time": now,
                "voice": {"media_id": "media-voice"},
            },
            {
                "origin": 4,
                "msgtype": "event",
                "msgid": "system-1",
                "external_userid": "user-1",
            },
        ],
    }
    queue = FakeKfQueue()
    processor = KfCallbackProcessor(FakeKfClient(sync_result), queue)

    await processor.handle_callback({"Token": "token-1", "OpenKfId": "kf-1"})

    assert [msg.msg_id for msg in queue.messages] == ["fresh-text", "image-1"]
    assert queue.messages[0].open_kfid == "kf-1"
    assert queue.messages[0].content == "想订生日蛋糕"
    assert queue.messages[1].msgtype == "image"
    assert queue.messages[1].media_id == "media-1"


@pytest.mark.asyncio
async def test_processor_skips_messages_when_session_is_inactive(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await prepare_kf_db(tmp_path, monkeypatch)
    sync_result = {
        "errcode": 0,
        "msg_list": [
            {
                "origin": 3,
                "msgtype": "text",
                "msgid": "text-1",
                "external_userid": "user-1",
                "text": {"content": "你好"},
            }
        ],
    }
    queue = FakeKfQueue()
    client = FakeKfClient(sync_result, inactive_users={"user-1"})
    processor = KfCallbackProcessor(client, queue)

    await processor.handle_callback({"Token": "token-1", "OpenKfId": "kf-1"})

    assert queue.messages == []
    assert client.checked_users == ["user-1"]


@pytest.mark.asyncio
async def test_processor_ignores_callback_without_token() -> None:
    queue = FakeKfQueue()
    processor = KfCallbackProcessor(FakeKfClient({"errcode": 0}), queue)

    await processor.handle_callback({"OpenKfId": "kf-1"})

    assert queue.messages == []


@pytest.mark.asyncio
async def test_processor_persists_servicer_message_without_ai_queue(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "kf-sync.db"
    monkeypatch.setattr("app.database.settings.DB_PATH", str(db_path))
    monkeypatch.setattr(
        "app.service.wecom.kf_handoff_checker.settings.WECOM_KF_SESSION_IDLE_CLOSE_SECONDS",
        24 * 60 * 60,
    )
    db = await init_db(str(db_path))
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status, extra_info, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "session-human",
            "wecom_kf",
            "user-1",
            "human_service",
            "{}",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    await db.commit()
    await close_db(db)

    sync_result = {
        "errcode": 0,
        "msg_list": [
            {
                "origin": 5,
                "msgtype": "text",
                "msgid": "staff-text-1",
                "external_userid": "user-1",
                "text": {"content": "最终确认芒果千层，少甜。"},
            }
        ],
    }
    queue = FakeKfQueue()
    processor = KfCallbackProcessor(FakeKfClient(sync_result), queue)

    await processor.handle_callback({"Token": "token-1", "OpenKfId": "kf-1"})

    assert queue.messages == []
    verify_db = await init_db(str(db_path))
    rows = await verify_db.execute_fetchall(
        "SELECT role, content, channel_msg_id FROM messages WHERE session_id = ?",
        ("session-human",),
    )
    sessions = await verify_db.execute_fetchall(
        "SELECT extra_info FROM sessions WHERE id = ?",
        ("session-human",),
    )
    await close_db(verify_db)

    assert len(rows) == 1
    assert rows[0]["role"] == "assistant"
    assert "最终确认芒果千层" in rows[0]["content"]
    assert rows[0]["channel_msg_id"] == "staff-text-1"
    assert SessionScope.BOT_THEN_HUMAN_SYNCED.value in sessions[0]["extra_info"]


@pytest.mark.asyncio
async def test_processor_pages_sync_and_persists_cursor(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = await prepare_kf_db(tmp_path, monkeypatch)
    pages = [
        {
            "errcode": 0,
            "has_more": 1,
            "next_cursor": "cursor-1",
            "msg_list": [
                {
                    "origin": 3,
                    "msgtype": "text",
                    "msgid": "page-text-1",
                    "external_userid": "user-1",
                    "text": {"content": "第一页"},
                }
            ],
        },
        {
            "errcode": 0,
            "has_more": 0,
            "next_cursor": "cursor-2",
            "msg_list": [
                {
                    "origin": 3,
                    "msgtype": "text",
                    "msgid": "page-text-2",
                    "external_userid": "user-1",
                    "text": {"content": "第二页"},
                }
            ],
        },
    ]
    client = FakeKfClient(pages)
    queue = FakeKfQueue()

    await KfCallbackProcessor(client, queue).handle_callback(
        {"Token": "token-1", "OpenKfId": "kf-1"}
    )

    assert client.cursors == ["", "cursor-1"]
    assert [msg.msg_id for msg in queue.messages] == ["page-text-1", "page-text-2"]
    verify_db = await init_db(db_path)
    rows = await verify_db.execute_fetchall(
        "SELECT last_cursor FROM wecom_kf_sync_states WHERE open_kfid = ?",
        ("kf-1",),
    )
    await close_db(verify_db)
    assert rows[0]["last_cursor"] == "cursor-2"


@pytest.mark.asyncio
async def test_handoff_user_message_is_synced_without_ai_queue(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "kf-sync.db"
    monkeypatch.setattr("app.database.settings.DB_PATH", str(db_path))
    monkeypatch.setattr(
        "app.service.wecom.kf_handoff_checker.settings.WECOM_KF_SESSION_IDLE_CLOSE_SECONDS",
        24 * 60 * 60,
    )
    db = await init_db(str(db_path))
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status, extra_info, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "session-human",
            "wecom_kf",
            "user-1",
            "human_service",
            "{}",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    await db.commit()
    await close_db(db)
    sync_result = {
        "errcode": 0,
        "msg_list": [
            {
                "origin": 3,
                "msgtype": "text",
                "msgid": "handoff-user-1",
                "external_userid": "user-1",
                "text": {"content": "人工阶段用户补充地址"},
            }
        ],
    }
    queue = FakeKfQueue()

    await KfCallbackProcessor(FakeKfClient(sync_result), queue).handle_callback(
        {"Token": "token-1", "OpenKfId": "kf-1"}
    )

    assert queue.messages == []
    verify_db = await init_db(str(db_path))
    rows = await verify_db.execute_fetchall(
        "SELECT role, content, channel_msg_id FROM messages WHERE session_id = ?",
        ("session-human",),
    )
    await close_db(verify_db)
    assert len(rows) == 1
    assert rows[0]["role"] == "user"
    assert rows[0]["channel_msg_id"] == "handoff-user-1"


@pytest.mark.asyncio
async def test_idle_handoff_session_is_closed_and_message_requeued(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "kf-sync.db"
    monkeypatch.setattr("app.database.settings.DB_PATH", str(db_path))
    monkeypatch.setattr(
        "app.service.wecom.kf_handoff_checker.settings.WECOM_KF_SESSION_IDLE_CLOSE_SECONDS",
        7200,
    )
    db = await init_db(str(db_path))
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status, extra_info, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "session-human-old",
            "wecom_kf",
            "user-1",
            "human_service",
            "{}",
            "2026-06-10 10:00:00",
        ),
    )
    await db.commit()
    await close_db(db)
    monkeypatch.setattr(
        "app.service.wecom.kf_handoff_checker.datetime",
        _FixedDatetime,
    )
    sync_result = {
        "errcode": 0,
        "msg_list": [
            {
                "origin": 3,
                "msgtype": "text",
                "msgid": "new-after-idle",
                "external_userid": "user-1",
                "text": {"content": "重新咨询"},
            }
        ],
    }
    queue = FakeKfQueue()

    await KfCallbackProcessor(FakeKfClient(sync_result), queue).handle_callback(
        {"Token": "token-1", "OpenKfId": "kf-1"}
    )

    assert [msg.msg_id for msg in queue.messages] == ["new-after-idle"]
    verify_db = await init_db(str(db_path))
    sessions = await verify_db.execute_fetchall(
        "SELECT status FROM sessions WHERE id = ?",
        ("session-human-old",),
    )
    await close_db(verify_db)
    assert sessions[0]["status"] == SessionStatus.CLOSED.value


@pytest.mark.asyncio
async def test_replyable_wecom_state_closes_stale_handoff_and_requeues(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "kf-sync.db"
    monkeypatch.setattr("app.database.settings.DB_PATH", str(db_path))
    db = await init_db(str(db_path))
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status, extra_info, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "session-stale-handoff",
            "wecom_kf",
            "user-1",
            "transfer_pending",
            "{}",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    await db.commit()
    await close_db(db)
    sync_result = {
        "errcode": 0,
        "msg_list": [
            {
                "origin": 3,
                "msgtype": "text",
                "msgid": "new-after-platform-end",
                "external_userid": "user-1",
                "text": {"content": "继续咨询"},
            }
        ],
    }
    client = FakeKfClient(sync_result, service_states={"user-1": 4})
    queue = FakeKfQueue()

    await KfCallbackProcessor(client, queue).handle_callback(
        {"Token": "token-1", "OpenKfId": "kf-1"}
    )

    assert [msg.msg_id for msg in queue.messages] == ["new-after-platform-end"]
    assert client.service_state_checks == ["user-1"]
    verify_db = await init_db(str(db_path))
    sessions = await verify_db.execute_fetchall(
        "SELECT status FROM sessions WHERE id = ?",
        ("session-stale-handoff",),
    )
    await close_db(verify_db)
    assert sessions[0]["status"] == SessionStatus.CLOSED.value


@pytest.mark.asyncio
async def test_active_human_wecom_state_still_blocks_ai_queue(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "kf-sync.db"
    monkeypatch.setattr("app.database.settings.DB_PATH", str(db_path))
    db = await init_db(str(db_path))
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status, extra_info, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "session-human",
            "wecom_kf",
            "user-1",
            "human_service",
            "{}",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    await db.commit()
    await close_db(db)
    sync_result = {
        "errcode": 0,
        "msg_list": [
            {
                "origin": 3,
                "msgtype": "text",
                "msgid": "human-still-active",
                "external_userid": "user-1",
                "text": {"content": "人工还在聊"},
            }
        ],
    }
    client = FakeKfClient(sync_result, service_states={"user-1": 3})
    queue = FakeKfQueue()

    await KfCallbackProcessor(client, queue).handle_callback(
        {"Token": "token-1", "OpenKfId": "kf-1"}
    )

    assert queue.messages == []
    assert client.service_state_checks == ["user-1"]


@pytest.mark.asyncio
async def test_same_page_handoff_event_prevents_ai_queue(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "kf-sync.db"
    monkeypatch.setattr("app.database.settings.DB_PATH", str(db_path))
    db = await init_db(str(db_path))
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status, extra_info) "
        "VALUES (?, ?, ?, ?, ?)",
        ("session-human", "wecom_kf", "user-1", "transfer_pending", "{}"),
    )
    await db.commit()
    await close_db(db)
    sync_result = {
        "errcode": 0,
        "msg_list": [
            {
                "origin": 4,
                "msgtype": "event",
                "msgid": "event-start-1",
                "external_userid": "user-1",
                "event": {
                    "event_type": "session_status_change",
                    "change_type": 1,
                },
            },
            {
                "origin": 3,
                "msgtype": "text",
                "msgid": "handoff-user-same-page",
                "external_userid": "user-1",
                "text": {"content": "同批次人工阶段消息"},
            },
        ],
    }
    queue = FakeKfQueue()

    await KfCallbackProcessor(FakeKfClient(sync_result), queue).handle_callback(
        {"Token": "token-1", "OpenKfId": "kf-1"}
    )

    assert queue.messages == []
    verify_db = await init_db(str(db_path))
    rows = await verify_db.execute_fetchall(
        "SELECT role, channel_msg_id FROM messages WHERE session_id = ?",
        ("session-human",),
    )
    sessions = await verify_db.execute_fetchall(
        "SELECT status FROM sessions WHERE id = ?",
        ("session-human",),
    )
    await close_db(verify_db)
    assert rows[0]["role"] == "user"
    assert rows[0]["channel_msg_id"] == "handoff-user-same-page"
    assert sessions[0]["status"] == SessionStatus.HUMAN_SERVICE.value


@pytest.mark.asyncio
async def test_start_event_sends_welcome_event_text(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "kf-sync.db"
    monkeypatch.setattr("app.database.settings.DB_PATH", str(db_path))
    monkeypatch.setattr(
        "app.service.wecom.kf_callback_processor.settings.WECOM_KF_WELCOME_TEXT",
        "已接入智能助手",
    )
    db = await init_db(str(db_path))
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status, extra_info) "
        "VALUES (?, ?, ?, ?, ?)",
        ("session-human", "wecom_kf", "user-1", "transfer_pending", "{}"),
    )
    await db.commit()
    await close_db(db)
    sync_result = {
        "errcode": 0,
        "msg_list": [
            {
                "origin": 4,
                "msgtype": "event",
                "msgid": "event-start-welcome",
                "external_userid": "user-1",
                "event": {
                    "event_type": "session_status_change",
                    "change_type": 1,
                    "welcome_code": "welcome-code-1",
                },
            }
        ],
    }
    client = FakeKfClient(sync_result)

    await KfCallbackProcessor(client, FakeKfQueue()).handle_callback(
        {"Token": "token-1", "OpenKfId": "kf-1"}
    )

    assert client.event_texts == [("welcome-code-1", "已接入智能助手", "")]


@pytest.mark.asyncio
async def test_session_end_event_closes_session_and_transfer(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "kf-sync.db"
    monkeypatch.setattr("app.database.settings.DB_PATH", str(db_path))
    db = await init_db(str(db_path))
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status, extra_info) "
        "VALUES (?, ?, ?, ?, ?)",
        ("session-human", "wecom_kf", "user-1", "human_service", "{}"),
    )
    await db.execute(
        "INSERT INTO human_transfers (id, session_id, user_id, status) "
        "VALUES (?, ?, ?, ?)",
        ("transfer-1", "session-human", "user-1", "accepted"),
    )
    await db.commit()
    await close_db(db)
    sync_result = {
        "errcode": 0,
        "msg_list": [
            {
                "origin": 4,
                "msgtype": "event",
                "msgid": "event-end-1",
                "external_userid": "user-1",
                "event": {
                    "event_type": "session_status_change",
                    "change_type": 3,
                },
            }
        ],
    }

    await KfCallbackProcessor(FakeKfClient(sync_result), FakeKfQueue()).handle_callback(
        {"Token": "token-1", "OpenKfId": "kf-1"}
    )

    verify_db = await init_db(str(db_path))
    sessions = await verify_db.execute_fetchall(
        "SELECT status FROM sessions WHERE id = ?",
        ("session-human",),
    )
    transfers = await verify_db.execute_fetchall(
        "SELECT status FROM human_transfers WHERE id = ?",
        ("transfer-1",),
    )
    await close_db(verify_db)
    assert sessions[0]["status"] == SessionStatus.CLOSED.value
    assert transfers[0]["status"] == TransferStatus.CLOSED.value


@pytest.mark.asyncio
async def test_message_after_same_batch_end_event_reenters_ai_queue(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "kf-sync.db"
    monkeypatch.setattr("app.database.settings.DB_PATH", str(db_path))
    db = await init_db(str(db_path))
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status, extra_info) "
        "VALUES (?, ?, ?, ?, ?)",
        ("session-human", "wecom_kf", "user-1", "human_service", "{}"),
    )
    await db.execute(
        "INSERT INTO human_transfers (id, session_id, user_id, status) "
        "VALUES (?, ?, ?, ?)",
        ("transfer-1", "session-human", "user-1", "accepted"),
    )
    await db.commit()
    await close_db(db)
    sync_result = {
        "errcode": 0,
        "msg_list": [
            {
                "origin": 4,
                "msgtype": "event",
                "msgid": "event-end-1",
                "external_userid": "user-1",
                "event": {
                    "event_type": "session_status_change",
                    "change_type": 3,
                },
            },
            {
                "origin": 3,
                "msgtype": "text",
                "msgid": "new-after-end",
                "external_userid": "user-1",
                "text": {"content": "new question"},
            },
        ],
    }
    queue = FakeKfQueue()

    await KfCallbackProcessor(FakeKfClient(sync_result), queue).handle_callback(
        {"Token": "token-1", "OpenKfId": "kf-1"}
    )

    assert [msg.msg_id for msg in queue.messages] == ["new-after-end"]
    verify_db = await init_db(str(db_path))
    sessions = await verify_db.execute_fetchall(
        "SELECT status FROM sessions WHERE id = ?",
        ("session-human",),
    )
    transfers = await verify_db.execute_fetchall(
        "SELECT status FROM human_transfers WHERE id = ?",
        ("transfer-1",),
    )
    await close_db(verify_db)
    assert sessions[0]["status"] == SessionStatus.CLOSED.value
    assert transfers[0]["status"] == TransferStatus.CLOSED.value


@pytest.mark.asyncio
async def test_empty_user_end_event_closes_single_active_handoff_session(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "kf-sync.db"
    monkeypatch.setattr("app.database.settings.DB_PATH", str(db_path))
    db = await init_db(str(db_path))
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status, extra_info) "
        "VALUES (?, ?, ?, ?, ?)",
        ("session-human", "wecom_kf", "user-1", "transfer_pending", "{}"),
    )
    await db.execute(
        "INSERT INTO human_transfers (id, session_id, user_id, status) "
        "VALUES (?, ?, ?, ?)",
        ("transfer-1", "session-human", "user-1", "accepted"),
    )
    await db.commit()
    await close_db(db)
    sync_result = {
        "errcode": 0,
        "msg_list": [
            {
                "origin": 4,
                "msgtype": "event",
                "msgid": "event-end-empty-user",
                "external_userid": "",
                "event": {
                    "event_type": "session_status_change",
                    "change_type": 3,
                },
            }
        ],
    }

    await KfCallbackProcessor(FakeKfClient(sync_result), FakeKfQueue()).handle_callback(
        {"Token": "token-1", "OpenKfId": "kf-1"}
    )

    verify_db = await init_db(str(db_path))
    sessions = await verify_db.execute_fetchall(
        "SELECT status FROM sessions WHERE id = ?",
        ("session-human",),
    )
    transfers = await verify_db.execute_fetchall(
        "SELECT status FROM human_transfers WHERE id = ?",
        ("transfer-1",),
    )
    await close_db(verify_db)
    assert sessions[0]["status"] == SessionStatus.CLOSED.value
    assert transfers[0]["status"] == TransferStatus.CLOSED.value


@pytest.mark.asyncio
async def test_duplicate_msgid_does_not_replay_after_callback(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await prepare_kf_db(tmp_path, monkeypatch)
    sync_result = {
        "errcode": 0,
        "msg_list": [
            {
                "origin": 3,
                "msgtype": "text",
                "msgid": "dup-text-1",
                "external_userid": "user-1",
                "text": {"content": "不要重复回复"},
            }
        ],
    }
    queue = FakeKfQueue()
    processor = KfCallbackProcessor(FakeKfClient(sync_result), queue)

    await processor.handle_callback({"Token": "token-1", "OpenKfId": "kf-1"})
    await processor.handle_callback({"Token": "token-1", "OpenKfId": "kf-1"})

    assert [msg.msg_id for msg in queue.messages] == ["dup-text-1"]


@pytest.mark.asyncio
async def test_kf_queue_skips_auto_reply_when_human_service_is_active(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "kf-sync.db"
    monkeypatch.setattr("app.database.settings.DB_PATH", str(db_path))
    db = await init_db(str(db_path))
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status, extra_info, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "session-human",
            "wecom_kf",
            "user-1",
            "human_service",
            "{}",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    await db.commit()
    await close_db(db)

    queue = KfMessageQueue()
    queue._chat_service = FakeChatService()  # noqa: SLF001
    await queue._process_one(  # noqa: SLF001
        KfIncomingMessage(
            external_userid="user-1",
            open_kfid="kf-1",
            content="我想再问一下",
            msg_id="text-1",
        )
    )

    assert queue._chat_service.calls == []  # noqa: SLF001


@pytest.mark.asyncio
async def test_kf_queue_skips_nontext_auto_reply_when_human_service_is_active(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "kf-sync.db"
    monkeypatch.setattr("app.database.settings.DB_PATH", str(db_path))
    db = await init_db(str(db_path))
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status, extra_info, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "session-human",
            "wecom_kf",
            "user-1",
            "transfer_pending",
            "{}",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    await db.commit()
    await close_db(db)

    queue = KfMessageQueue()
    queue._chat_service = FakeChatService()  # noqa: SLF001
    await queue._process_one(  # noqa: SLF001
        KfIncomingMessage(
            external_userid="user-1",
            open_kfid="kf-1",
            content="[image消息]",
            msg_id="image-1",
            msgtype="image",
            media_id="media-1",
        )
    )

    assert queue._chat_service.calls == []  # noqa: SLF001
