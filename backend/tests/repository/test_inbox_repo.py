"""持久 inbox 状态机测试。"""

import pytest

from app.repository.inbox_repo import InboxRepo, MAX_INBOX_ATTEMPTS


@pytest.mark.asyncio
async def test_inbox_claim_and_processed_are_idempotent(db) -> None:
    repo = InboxRepo(db)

    assert await repo.enqueue("wecom", "wecom:msg-1", '{"content":"hello"}') is True
    assert await repo.enqueue("wecom", "wecom:msg-1", '{"content":"replay"}') is False
    claimed = await repo.claim("wecom")
    assert claimed is not None
    assert claimed["message_key"] == "wecom:msg-1"
    assert claimed["attempt_count"] == 1

    await repo.mark_processed("wecom:msg-1")
    assert await repo.claim("wecom") is None
    assert await repo.count_pending("wecom") == 0


@pytest.mark.asyncio
async def test_inbox_expired_processing_lease_can_be_reclaimed(db) -> None:
    repo = InboxRepo(db)
    await repo.enqueue("wecom", "wecom:lease-1", "{}")
    first = await repo.claim("wecom", lease_seconds=-60)
    second = await repo.claim("wecom", lease_seconds=60)

    assert first is not None
    assert second is not None
    assert second["message_key"] == "wecom:lease-1"
    assert second["attempt_count"] == 2


@pytest.mark.asyncio
async def test_inbox_counts_expired_processing_as_stuck(db) -> None:
    repo = InboxRepo(db)
    await repo.enqueue("wecom", "wecom:stuck-1", "{}")
    await repo.claim("wecom", lease_seconds=-60)

    assert await repo.count_stuck("wecom") == 1


@pytest.mark.asyncio
async def test_inbox_moves_to_dead_letter_after_bounded_failures(db) -> None:
    repo = InboxRepo(db)
    await repo.enqueue("wecom", "wecom:failed-1", "{}")

    for attempt in range(MAX_INBOX_ATTEMPTS):
        claimed = await repo.claim("wecom")
        assert claimed is not None
        await repo.mark_failed("wecom:failed-1", f"failure-{attempt}")
        await db.execute(
            "UPDATE inbox_events SET next_attempt_at = '2000-01-01 00:00:00' "
            "WHERE message_key = ?",
            ("wecom:failed-1",),
        )
        await db.commit()

    assert await repo.claim("wecom") is None
    rows = await db.execute_fetchall(
        "SELECT status, attempt_count, last_error FROM inbox_events "
        "WHERE message_key = ?",
        ("wecom:failed-1",),
    )
    assert dict(rows[0]) == {
        "status": "dead_letter",
        "attempt_count": MAX_INBOX_ATTEMPTS,
        "last_error": "failure-4",
    }


@pytest.mark.asyncio
async def test_renew_or_validate_lease_ownership(db) -> None:
    """B3.5（问题 8）：claim_token 语义——attempt_count 匹配且 lease 有效才续租。"""
    repo = InboxRepo(db)
    await repo.enqueue("wecom", "wecom:owned-1", "{}")
    claimed = await repo.claim("wecom", lease_seconds=60)
    assert claimed is not None
    assert claimed["attempt_count"] == 1
    # 当前持有者（attempt 1）lease 有效：续租成功（业务写可继续）
    assert (
        await repo.renew_or_validate_lease("wecom:owned-1", expected_attempt=1) is True
    )
    # 原 worker lease 过期后被另一 worker 接管（attempt +1）
    await db.execute(
        "UPDATE inbox_events SET lease_until = '2000-01-01 00:00:00' "
        "WHERE message_key = 'wecom:owned-1'"
    )
    await db.commit()
    taken = await repo.claim("wecom", lease_seconds=60)
    assert taken is not None
    assert taken["attempt_count"] == 2
    # 陈旧 worker（旧 attempt）校验失败 → 不得继续业务写
    assert (
        await repo.renew_or_validate_lease("wecom:owned-1", expected_attempt=1) is False
    )
    # 新持有者（attempt 2）校验成功
    assert (
        await repo.renew_or_validate_lease("wecom:owned-1", expected_attempt=2) is True
    )
