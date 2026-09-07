"""有赞通知审计与收件箱同事务提交测试。"""

import ast
import json
from pathlib import Path

import pytest

from app.config import settings
from app.database import close_db, db_session_scope, init_db
from app.models.youzan_webhook_event import (
    YouzanWebhookBusinessType,
    YouzanWebhookEventCreate,
    YouzanWebhookEventUpdate,
    YouzanWebhookStatus,
)
from app.repository.inbox_repo import InboxRepo
from app.repository.youzan_webhook_event_repo import YouzanWebhookEventRepo


@pytest.fixture
async def uow_db(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """每个用例独享文件数据库，支持跨连接断言最终状态。"""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "webhook-uow.db"))
    connection = await init_db(settings.DB_PATH)
    await close_db(connection)
    yield settings.DB_PATH


def _audit_event(msg_id: str, trace_id: str) -> YouzanWebhookEventCreate:
    """构造最小审计收件事实。"""
    return YouzanWebhookEventCreate(
        msg_id=msg_id,
        trace_id=trace_id,
        event_type="trade_TradeBuyerPay",
        business_type=YouzanWebhookBusinessType.TRADE,
        business_key="E202609060001",
        http_status=200,
        payload_hash="hash-uow",
        payload_summary_json=json.dumps({"tid": "E202609060001"}),
    )


def test_audit_repo_write_methods_have_no_internal_commit() -> None:
    """静态守卫：审计仓储写方法不得自提交，事务由调用方持有。"""
    repo_path = (
        Path(__file__).resolve().parents[3]
        / "app"
        / "repository"
        / "youzan_webhook_event_repo.py"
    )
    tree = ast.parse(repo_path.read_text(encoding="utf-8"))
    target_class = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "YouzanWebhookEventRepo"
    )
    write_methods = {"create_received", "mark_processing", "mark_result"}
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
async def test_ingress_audit_and_inbox_rollback_together(uow_db: str) -> None:
    """收件阶段失败时审计与收件箱一起回滚，不留半完成事实。"""
    with pytest.raises(RuntimeError, match="模拟业务写入失败"):
        async with db_session_scope():
            audit_repo = YouzanWebhookEventRepo()
            inbox_repo = InboxRepo()
            await audit_repo.create_received(_audit_event("uow-ingress-1", "trace-1"))
            await inbox_repo.enqueue(
                "youzan_webhook",
                "youzan_webhook:uow-ingress-1",
                json.dumps({"msg_id": "uow-ingress-1"}),
            )
            raise RuntimeError("模拟业务写入失败")
    async with db_session_scope():
        assert await YouzanWebhookEventRepo().get_by_msg_id("uow-ingress-1") is None
        rows = await InboxRepo()._db.execute_fetchall(
            "SELECT id FROM inbox_events WHERE message_key = ?",
            ("youzan_webhook:uow-ingress-1",),
        )
        assert rows == []


@pytest.mark.asyncio
async def test_ingress_duplicate_webhook_is_idempotent(uow_db: str) -> None:
    """重复投递只保留一条审计事实和一条收件箱事实。"""
    async with db_session_scope():
        audit_repo = YouzanWebhookEventRepo()
        inbox_repo = InboxRepo()
        first_id = await audit_repo.create_received(
            _audit_event("uow-dup-1", "trace-a")
        )
        first_queued = await inbox_repo.enqueue(
            "youzan_webhook",
            "youzan_webhook:uow-dup-1",
            json.dumps({"msg_id": "uow-dup-1"}),
        )
        second_id = await audit_repo.create_received(
            _audit_event("uow-dup-1", "trace-b")
        )
        second_queued = await inbox_repo.enqueue(
            "youzan_webhook",
            "youzan_webhook:uow-dup-1",
            json.dumps({"msg_id": "uow-dup-1"}),
        )
        assert first_queued is True
        assert second_queued is False
        assert second_id == first_id
    async with db_session_scope():
        row = await YouzanWebhookEventRepo().get_by_msg_id("uow-dup-1")
        assert row is not None
        assert row["status"] == YouzanWebhookStatus.DUPLICATE
        assert row["trace_id"] == "trace-b"
        rows = await InboxRepo()._db.execute_fetchall(
            "SELECT id FROM inbox_events WHERE message_key = ?",
            ("youzan_webhook:uow-dup-1",),
        )
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_worker_business_failure_rolls_back_audit_and_inbox(uow_db: str) -> None:
    """业务写入失败时审计结果与收件箱完成标记一起回滚。"""
    async with db_session_scope():
        audit_id = await YouzanWebhookEventRepo().create_received(
            _audit_event("uow-worker-1", "trace-w1")
        )
        await InboxRepo().enqueue(
            "youzan_webhook",
            "youzan_webhook:uow-worker-1",
            json.dumps({"msg_id": "uow-worker-1"}),
        )
    with pytest.raises(RuntimeError, match="模拟业务处理失败"):
        async with db_session_scope():
            audit_repo = YouzanWebhookEventRepo()
            inbox_repo = InboxRepo()
            await audit_repo.mark_processing(audit_id, "worker_dispatched")
            await inbox_repo._db.execute(
                "INSERT INTO sessions (id, channel, user_id) VALUES (?, ?, ?)",
                ("session-uow-1", "youzan", "buyer-uow-1"),
            )
            raise RuntimeError("模拟业务处理失败")
    async with db_session_scope():
        audit_row = await YouzanWebhookEventRepo().get_by_msg_id("uow-worker-1")
        assert audit_row is not None
        assert audit_row["status"] == YouzanWebhookStatus.RECEIVED
        inbox_rows = await InboxRepo()._db.execute_fetchall(
            "SELECT status FROM inbox_events WHERE message_key = ?",
            ("youzan_webhook:uow-worker-1",),
        )
        assert dict(inbox_rows[0])["status"] == "received"
        business_rows = await InboxRepo()._db.execute_fetchall(
            "SELECT id FROM sessions WHERE id = ?",
            ("session-uow-1",),
        )
        assert business_rows == []


@pytest.mark.asyncio
async def test_worker_audit_failure_rolls_back_business(uow_db: str) -> None:
    """审计写入失败时业务写入一起回滚，不留孤立业务事实。"""
    async with db_session_scope():
        audit_id = await YouzanWebhookEventRepo().create_received(
            _audit_event("uow-worker-2", "trace-w2")
        )
        await InboxRepo().enqueue(
            "youzan_webhook",
            "youzan_webhook:uow-worker-2",
            json.dumps({"msg_id": "uow-worker-2"}),
        )
    with pytest.raises(RuntimeError, match="模拟审计写入失败"):
        async with db_session_scope():
            audit_repo = YouzanWebhookEventRepo()
            await audit_repo._db.execute(
                "INSERT INTO sessions (id, channel, user_id) VALUES (?, ?, ?)",
                ("session-uow-2", "youzan", "buyer-uow-2"),
            )
            await audit_repo.mark_result(
                audit_id,
                YouzanWebhookEventUpdate(
                    status=YouzanWebhookStatus.PROCESSED,
                    process_stage="worker_processed",
                ),
            )
            raise RuntimeError("模拟审计写入失败")
    async with db_session_scope():
        audit_row = await YouzanWebhookEventRepo().get_by_msg_id("uow-worker-2")
        assert audit_row is not None
        assert audit_row["status"] == YouzanWebhookStatus.RECEIVED
        business_rows = await InboxRepo()._db.execute_fetchall(
            "SELECT id FROM sessions WHERE id = ?",
            ("session-uow-2",),
        )
        assert business_rows == []


@pytest.mark.asyncio
async def test_savepoint_rolls_back_only_inner_business(uow_db: str) -> None:
    """保存点失败只回滚内部业务，审计与收件箱仍可提交。"""
    async with db_session_scope():
        audit_repo = YouzanWebhookEventRepo()
        inbox_repo = InboxRepo()
        await audit_repo.create_received(_audit_event("uow-savepoint-1", "trace-s1"))
        await inbox_repo.enqueue(
            "youzan_webhook",
            "youzan_webhook:uow-savepoint-1",
            json.dumps({"msg_id": "uow-savepoint-1"}),
        )
        try:
            async with audit_repo.transaction():
                await audit_repo._db.execute(
                    "INSERT INTO sessions (id, channel, user_id) VALUES (?, ?, ?)",
                    ("session-uow-sp", "youzan", "buyer-uow-sp"),
                )
                raise RuntimeError("模拟内部业务失败")
        except RuntimeError:
            pass
    async with db_session_scope():
        assert (
            await YouzanWebhookEventRepo().get_by_msg_id("uow-savepoint-1")
        ) is not None
        inbox_rows = await InboxRepo()._db.execute_fetchall(
            "SELECT id FROM inbox_events WHERE message_key = ?",
            ("youzan_webhook:uow-savepoint-1",),
        )
        assert len(inbox_rows) == 1
        business_rows = await InboxRepo()._db.execute_fetchall(
            "SELECT id FROM sessions WHERE id = ?",
            ("session-uow-sp",),
        )
        assert business_rows == []
