"""
SessionRepo 数据访问层单元测试。

覆盖：get_or_create 幂等性、get_active 状态过滤、
update_status 状态流转、get_all_active 活跃会话查询。
"""

import aiosqlite
import pytest
from datetime import datetime

from app.models.session import Channel, SessionCreate, SessionStatus
from app.repository.session_repo import SessionRepo


@pytest.fixture
def repo(db: aiosqlite.Connection) -> SessionRepo:
    """每个测试使用同一个内存库连接构建仓库实例。"""
    return SessionRepo(db)


async def test_get_or_create_new_session(repo: SessionRepo) -> None:
    """不存在活跃会话时应自动创建并返回新会话。"""
    data = SessionCreate(id="s-001", channel=Channel.YOUZAN, user_id="buyer_001")
    session = await repo.get_or_create(data)

    assert session.id == "s-001"
    assert session.channel == Channel.YOUZAN
    assert session.user_id == "buyer_001"
    assert session.status == SessionStatus.ACTIVE


async def test_get_or_create_returns_existing_active_session(repo: SessionRepo) -> None:
    """同一用户同一渠道多次调用应返回同一活跃会话（幂等）。"""
    data = SessionCreate(id="s-002", channel=Channel.YOUZAN, user_id="buyer_002")
    first = await repo.get_or_create(data)
    second = await repo.get_or_create(data)

    assert first.id == second.id


async def test_get_or_create_creates_new_after_closed(repo: SessionRepo) -> None:
    """旧会话关闭后，同用户下次应创建新会话。"""
    data = SessionCreate(id="s-003", channel=Channel.YOUZAN, user_id="buyer_003")
    old = await repo.get_or_create(data)
    await repo.update_status(old.id, SessionStatus.CLOSED)

    new_data = SessionCreate(id="s-003b", channel=Channel.YOUZAN, user_id="buyer_003")
    new = await repo.get_or_create(new_data)

    assert new.id == "s-003b"


async def test_get_active_ignores_closed_session(repo: SessionRepo) -> None:
    """get_active 不应返回已关闭的会话。"""
    data = SessionCreate(id="s-004", channel=Channel.YOUZAN, user_id="buyer_004")
    session = await repo.get_or_create(data)
    await repo.update_status(session.id, SessionStatus.CLOSED)

    result = await repo.get_active("buyer_004", Channel.YOUZAN)
    assert result is None


async def test_update_status_transfer_pending(repo: SessionRepo) -> None:
    """update_status 应正确将会话标记为 transfer_pending。"""
    data = SessionCreate(id="s-005", channel=Channel.YOUZAN, user_id="buyer_005")
    session = await repo.get_or_create(data)
    await repo.update_status(session.id, SessionStatus.TRANSFER_PENDING)

    updated = await repo.get(session.id)
    assert updated is not None
    assert updated.status == SessionStatus.TRANSFER_PENDING


async def test_get_all_active_excludes_closed(repo: SessionRepo) -> None:
    """get_all_active 只返回 active / transfer_pending / human_service 三种状态。"""
    for i, status in enumerate(
        [SessionStatus.ACTIVE, SessionStatus.CLOSED, SessionStatus.HUMAN_SERVICE]
    ):
        data = SessionCreate(
            id=f"s-10{i}", channel=Channel.YOUZAN, user_id=f"buyer_10{i}"
        )
        s = await repo.get_or_create(data)
        if status != SessionStatus.ACTIVE:
            await repo.update_status(s.id, status)

    active_list = await repo.get_all_active()
    ids = {s.id for s in active_list}

    assert "s-100" in ids
    assert "s-101" not in ids
    assert "s-102" in ids


async def test_get_returns_none_for_nonexistent(repo: SessionRepo) -> None:
    """查询不存在的会话 ID 应返回 None。"""
    result = await repo.get("nonexistent-id")
    assert result is None


async def test_close_idle_active_sessions_only_closes_old_sessions_with_messages(
    repo: SessionRepo,
    db: aiosqlite.Connection,
) -> None:
    """空闲收口只关闭有消息且超过阈值的 active 会话。"""
    old_with_message = await repo.get_or_create(
        SessionCreate(id="idle-old", channel=Channel.YOUZAN, user_id="buyer-old")
    )
    old_without_message = await repo.get_or_create(
        SessionCreate(id="idle-empty", channel=Channel.YOUZAN, user_id="buyer-empty")
    )
    fresh_with_message = await repo.get_or_create(
        SessionCreate(id="idle-fresh", channel=Channel.YOUZAN, user_id="buyer-fresh")
    )
    transfer_session = await repo.get_or_create(
        SessionCreate(
            id="idle-transfer",
            channel=Channel.YOUZAN,
            user_id="buyer-transfer",
        )
    )
    await repo.update_status(transfer_session.id, SessionStatus.TRANSFER_PENDING)
    await db.executemany(
        "INSERT INTO messages (id, session_id, role, content, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            ("msg-old", old_with_message.id, "user", "旧消息", "2026-06-24 10:00:00"),
            (
                "msg-fresh",
                fresh_with_message.id,
                "user",
                "新消息",
                "2026-06-24 10:20:00",
            ),
            (
                "msg-transfer",
                transfer_session.id,
                "user",
                "转人工消息",
                "2026-06-24 10:00:00",
            ),
        ],
    )
    await db.execute(
        "UPDATE sessions SET updated_at = ? WHERE id IN (?, ?, ?)",
        (
            "2026-06-24 10:00:00",
            old_with_message.id,
            old_without_message.id,
            transfer_session.id,
        ),
    )
    await db.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        ("2026-06-24 10:20:00", fresh_with_message.id),
    )
    await db.commit()

    closed_count = await repo.close_idle_active_sessions(
        30,
        now=datetime(2026, 6, 24, 10, 31, 0),
    )

    sessions = {
        str(row["id"]): str(row["status"])
        for row in await _fetch_session_statuses(
            db,
            [
                old_with_message.id,
                old_without_message.id,
                fresh_with_message.id,
                transfer_session.id,
            ],
        )
    }
    assert closed_count == 1
    assert sessions[old_with_message.id] == SessionStatus.CLOSED.value
    assert sessions[old_without_message.id] == SessionStatus.ACTIVE.value
    assert sessions[fresh_with_message.id] == SessionStatus.ACTIVE.value
    assert sessions[transfer_session.id] == SessionStatus.TRANSFER_PENDING.value


async def _fetch_session_statuses(
    db: aiosqlite.Connection,
    session_ids: list[str],
) -> list[aiosqlite.Row]:
    placeholders = ", ".join("?" for _ in session_ids)
    return await db.execute_fetchall(
        "SELECT id, status FROM sessions WHERE id IN (" + placeholders + ")",
        tuple(session_ids),
    )
