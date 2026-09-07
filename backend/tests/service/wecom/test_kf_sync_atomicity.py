"""企微同步游标与入队原子性测试。"""

import ast
from pathlib import Path

import pytest

from app.config import settings
from app.database import close_db, db_session_scope, init_db
from app.repository.inbox_repo import InboxRepo
from app.repository.wecom_kf_sync_repo import WecomKfSyncRepo
from app.service.wecom import kf_sync_persist as persist_module
from app.service.wecom.kf_callback_processor import KfCallbackProcessor
from app.service.wecom.kf_message_queue import KfIncomingMessage
from app.service.wecom.kf_sync_persist import stage_inbox_messages as real_stage


class FakeKfClient:
    """最小同步客户端，支持分页与失败注入。"""

    def __init__(self, sync_results: list[dict]) -> None:
        self.sync_results = sync_results
        self.calls = 0

    async def sync_kf_messages(self, kf_token: str, cursor: str = "") -> dict:
        index = min(self.calls, len(self.sync_results) - 1)
        self.calls += 1
        return self.sync_results[index]

    async def ensure_kf_session_active(self, external_userid: str) -> bool:
        return True

    async def get_kf_service_state(self, external_userid: str):
        return None

    async def send_kf_event_text(
        self, code: str, content: str, msgid: str = ""
    ) -> dict:
        return {"errcode": 0}


class FakeKfQueue:
    """内存通知队列，仅记录通知，不参与持久化。"""

    def __init__(self) -> None:
        self.messages: list[KfIncomingMessage] = []

    async def enqueue(self, msg: KfIncomingMessage) -> bool:
        self.messages.append(msg)
        return True


def _text_message(msg_id: str, content: str = "你好") -> dict:
    """构造单条客户文本消息。"""
    return {
        "origin": 3,
        "msgtype": "text",
        "msgid": msg_id,
        "external_userid": "user-1",
        "text": {"content": content},
    }


def _ok_page(messages: list[dict], cursor: str, has_more: int = 0) -> dict:
    """构造成功分页结果。"""
    return {
        "errcode": 0,
        "has_more": has_more,
        "next_cursor": cursor,
        "msg_list": messages,
    }


@pytest.fixture
async def sync_db(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """每个用例独享文件数据库。"""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "kf-atomic.db"))
    connection = await init_db(settings.DB_PATH)
    await close_db(connection)
    yield


def test_sync_repo_write_methods_have_no_internal_commit() -> None:
    """静态守卫：同步仓储写方法不得自提交，事务由同步命令持有。"""
    repo_path = (
        Path(__file__).resolve().parents[3]
        / "app"
        / "repository"
        / "wecom_kf_sync_repo.py"
    )
    tree = ast.parse(repo_path.read_text(encoding="utf-8"))
    target_class = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "WecomKfSyncRepo"
    )
    write_methods = {
        "mark_syncing",
        "mark_success",
        "mark_failed",
        "add_message_if_new",
    }
    observed: dict[str, bool] = {}
    for node in target_class.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name in write_methods:
            has_commit = any(
                isinstance(child, ast.Attribute) and child.attr == "commit"
                for child in ast.walk(node)
            )
            observed[node.name] = has_commit
    assert set(observed) == write_methods
    assert not any(observed.values())


@pytest.mark.asyncio
async def test_inbox_failure_keeps_cursor_behind(
    sync_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """收件箱暂存失败时游标不推进，账本一起回滚，重跑不丢消息。"""
    client = FakeKfClient([_ok_page([_text_message("cursor-behind-1")], "cursor-1")])
    queue = FakeKfQueue()
    processor = KfCallbackProcessor(client, queue)

    async def failing_stage(*args, **kwargs) -> int:
        raise RuntimeError("模拟收件箱写入失败")

    monkeypatch.setattr(persist_module, "stage_inbox_messages", failing_stage)
    with pytest.raises(RuntimeError, match="模拟收件箱写入失败"):
        await processor.handle_callback({"Token": "t", "OpenKfId": "kf-1"})
    async with db_session_scope():
        state = await WecomKfSyncRepo().get_state("kf-1")
        assert state.last_cursor == ""
        ledger_rows = await WecomKfSyncRepo()._db.execute_fetchall(
            "SELECT msg_id FROM wecom_kf_message_ledger WHERE msg_id = ?",
            ("cursor-behind-1",),
        )
        assert ledger_rows == []
        inbox_rows = await InboxRepo()._db.execute_fetchall(
            "SELECT id FROM inbox_events WHERE message_key = ?",
            ("wecom_kf:cursor-behind-1",),
        )
        assert inbox_rows == []
    assert queue.messages == []

    monkeypatch.setattr(persist_module, "stage_inbox_messages", real_stage)
    await processor.handle_callback({"Token": "t", "OpenKfId": "kf-1"})
    assert [msg.msg_id for msg in queue.messages] == ["cursor-behind-1"]
    async with db_session_scope():
        state = await WecomKfSyncRepo().get_state("kf-1")
        assert state.last_cursor == "cursor-1"


@pytest.mark.asyncio
async def test_duplicate_pull_produces_single_fact(sync_db) -> None:
    """同一外部消息重复拉取只产生一个幂等事实。"""
    page = _ok_page([_text_message("dup-kf-1")], "cursor-dup")
    processor = KfCallbackProcessor(FakeKfClient([page]), FakeKfQueue())
    await processor.handle_callback({"Token": "t", "OpenKfId": "kf-1"})

    second_queue = FakeKfQueue()
    second = KfCallbackProcessor(FakeKfClient([page]), second_queue)
    await second.handle_callback({"Token": "t", "OpenKfId": "kf-1"})

    assert second_queue.messages == []
    async with db_session_scope():
        ledger_rows = await WecomKfSyncRepo()._db.execute_fetchall(
            "SELECT msg_id FROM wecom_kf_message_ledger WHERE msg_id = ?",
            ("dup-kf-1",),
        )
        assert len(ledger_rows) == 1
        inbox_rows = await InboxRepo()._db.execute_fetchall(
            "SELECT id FROM inbox_events WHERE message_key = ?",
            ("wecom_kf:dup-kf-1",),
        )
        assert len(inbox_rows) == 1
        state = await WecomKfSyncRepo().get_state("kf-1")
        assert state.last_cursor == "cursor-dup"


@pytest.mark.asyncio
async def test_empty_page_advances_cursor_without_facts(sync_db) -> None:
    """空页推进游标且不产生消息事实。"""
    processor = KfCallbackProcessor(
        FakeKfClient([_ok_page([], "cursor-empty")]), FakeKfQueue()
    )
    await processor.handle_callback({"Token": "t", "OpenKfId": "kf-1"})

    async with db_session_scope():
        state = await WecomKfSyncRepo().get_state("kf-1")
        assert state.last_cursor == "cursor-empty"
        inbox_rows = await InboxRepo()._db.execute_fetchall(
            "SELECT id FROM inbox_events WHERE queue_name = ?",
            ("wecom_kf",),
        )
        assert inbox_rows == []


@pytest.mark.asyncio
async def test_partial_page_failure_rolls_back_and_recovers(sync_db) -> None:
    """第二页拉取失败时整体回滚，重跑后两页消息完整。"""
    first_page = _ok_page([_text_message("part-1")], "cursor-p1", has_more=1)
    failing = FakeKfClient([first_page, {"errcode": 1001, "errmsg": "限流"}])
    processor = KfCallbackProcessor(failing, FakeKfQueue())
    await processor.handle_callback({"Token": "t", "OpenKfId": "kf-1"})

    async with db_session_scope():
        state = await WecomKfSyncRepo().get_state("kf-1")
        assert state.last_cursor == ""
        assert state.status == "failed"
        ledger_rows = await WecomKfSyncRepo()._db.execute_fetchall(
            "SELECT msg_id FROM wecom_kf_message_ledger WHERE msg_id = ?",
            ("part-1",),
        )
        assert ledger_rows == []

    recovery_pages = [
        _ok_page([_text_message("part-1")], "cursor-p1", has_more=1),
        _ok_page([_text_message("part-2")], "cursor-p2"),
    ]
    queue = FakeKfQueue()
    await KfCallbackProcessor(FakeKfClient(recovery_pages), queue).handle_callback(
        {"Token": "t", "OpenKfId": "kf-1"}
    )
    assert [msg.msg_id for msg in queue.messages] == ["part-1", "part-2"]
    async with db_session_scope():
        state = await WecomKfSyncRepo().get_state("kf-1")
        assert state.last_cursor == "cursor-p2"
        assert state.status == "idle"


@pytest.mark.asyncio
async def test_savepoint_rolls_back_only_inner_write(sync_db) -> None:
    """保存点失败只回滚内部写入，游标推进仍可提交。"""
    async with db_session_scope():
        repo = WecomKfSyncRepo()
        await repo.mark_syncing("kf-sp")
        try:
            async with repo.transaction():
                await repo.add_message_if_new(
                    msg_id="sp-msg-1",
                    open_kfid="kf-sp",
                    external_userid="user-1",
                    origin=3,
                    msgtype="text",
                    event_type="",
                    process_action="route_customer",
                )
                raise RuntimeError("模拟内部写入失败")
        except RuntimeError:
            pass
        await repo.mark_success("kf-sp", "cursor-sp")
    async with db_session_scope():
        repo = WecomKfSyncRepo()
        state = await repo.get_state("kf-sp")
        assert state.last_cursor == "cursor-sp"
        ledger_rows = await repo._db.execute_fetchall(
            "SELECT msg_id FROM wecom_kf_message_ledger WHERE msg_id = ?",
            ("sp-msg-1",),
        )
        assert ledger_rows == []
