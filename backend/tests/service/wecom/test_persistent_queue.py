"""企微队列持久入队与重启恢复测试。"""

import pytest

from app.database import close_db, init_db
from app.config import settings
from app.service.wecom.kf_message_queue import KfIncomingMessage, KfMessageQueue
from app.service.wecom.message_queue import WeComIncomingMessage, WeComMessageQueue


@pytest.mark.asyncio
async def test_wecom_queue_recovers_message_after_queue_instance_restart(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "inbox.db"))
    connection = await init_db(settings.DB_PATH)
    await close_db(connection)
    first_queue = WeComMessageQueue()
    message = WeComIncomingMessage("user-1", "你好", "restart-1")

    assert await first_queue.enqueue(message) is True

    restarted_queue = WeComMessageQueue()
    claimed = await restarted_queue._claim_persisted_message()

    assert claimed == message
    await restarted_queue._mark_persisted_processed("wecom:restart-1")
    assert await restarted_queue._claim_persisted_message() is None


@pytest.mark.asyncio
async def test_kf_queue_duplicate_enqueue_is_acknowledged_without_duplicate_row(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "kf-inbox.db"))
    connection = await init_db(settings.DB_PATH)
    await close_db(connection)
    queue = KfMessageQueue()
    message = KfIncomingMessage(
        external_userid="user-1",
        open_kfid="kf-1",
        content="你好",
        msg_id="kf-msg-1",
    )

    assert await queue.enqueue(message) is True
    assert await queue.enqueue(message) is True
    claimed = await queue._claim_persisted_message()
    assert claimed == message
    await queue._mark_persisted_processed("wecom_kf:kf-msg-1")
