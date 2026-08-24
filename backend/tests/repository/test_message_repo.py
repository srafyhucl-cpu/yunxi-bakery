"""消息仓库的数据库幂等合同测试。"""

import asyncio

import pytest

from app.database import close_db, init_db
from app.models.message import Message, MessageRole
from app.repository.message_repo import MessageRepo


async def _insert_session(db: object, session_id: str = "session-1") -> None:
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id) VALUES (?, ?, ?)",
        (session_id, "youzan", "buyer-1"),
    )
    await db.commit()


def _message(channel_msg_id: str, message_id: str = "") -> Message:
    return Message(
        id=message_id,
        session_id="session-1",
        role=MessageRole.USER,
        content="你好",
        channel_msg_id=channel_msg_id,
    )


@pytest.mark.asyncio
async def test_save_if_new_replay_is_idempotent(db) -> None:
    await _insert_session(db)
    repo = MessageRepo(db)

    assert await repo.save_if_new(_message("replay-1")) is True
    assert await repo.save_if_new(_message("replay-1")) is False
    rows = await db.execute_fetchall(
        "SELECT COUNT(*) AS row_count FROM messages WHERE channel_msg_id = ?",
        ("replay-1",),
    )
    assert rows[0]["row_count"] == 1


@pytest.mark.asyncio
async def test_save_if_new_concurrent_claim_has_one_winner(tmp_path) -> None:
    db_path = tmp_path / "message-claim.db"
    first_db = await init_db(str(db_path))
    second_db = await init_db(str(db_path))
    try:
        await _insert_session(first_db)
        results = await asyncio.gather(
            MessageRepo(first_db).save_if_new(_message("concurrent-1")),
            MessageRepo(second_db).save_if_new(_message("concurrent-1")),
        )
        assert sorted(results) == [False, True]
        rows = await first_db.execute_fetchall(
            "SELECT COUNT(*) AS row_count FROM messages WHERE channel_msg_id = ?",
            ("concurrent-1",),
        )
        assert rows[0]["row_count"] == 1
    finally:
        await close_db(first_db)
        await close_db(second_db)


@pytest.mark.asyncio
async def test_save_if_new_rolls_back_claim_with_outer_transaction(db) -> None:
    await _insert_session(db)
    repo = MessageRepo(db)

    with pytest.raises(RuntimeError, match="rollback"):
        async with repo.transaction():
            assert await repo.save_if_new(_message("rollback-1")) is True
            raise RuntimeError("rollback")

    assert await repo.save_if_new(_message("rollback-1")) is True
