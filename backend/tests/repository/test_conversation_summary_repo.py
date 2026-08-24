"""客户会话短期摘要仓库测试。"""

import aiosqlite
import pytest

from app.models.conversation_summary import (
    ConversationSummaryCreate,
    ConversationSummaryStatus,
)
from app.repository.conversation_summary_repo import ConversationSummaryRepo


@pytest.fixture
def repo(db: aiosqlite.Connection) -> ConversationSummaryRepo:
    return ConversationSummaryRepo(db)


async def test_upsert_active_creates_readable_summary(
    db: aiosqlite.Connection,
    repo: ConversationSummaryRepo,
) -> None:
    await _insert_session(db, "session-summary-1", "buyer-1")

    summary = await repo.upsert_active(
        ConversationSummaryCreate(
            session_id="session-summary-1",
            channel="youzan",
            user_id="buyer-1",
            summary_text="客户想订低糖生日蛋糕。",
            state_json='{"pending_questions":["配送时间"]}',
            source_message_ids_json='["msg-1","msg-2"]',
            source_until_message_id="msg-2",
            token_estimate=32,
        )
    )
    active = await repo.get_active("session-summary-1")

    assert active is not None
    assert active.id == summary.id
    assert active.summary_text == "客户想订低糖生日蛋糕。"
    assert active.state_json == '{"pending_questions":["配送时间"]}'
    assert active.source_until_message_id == "msg-2"
    assert active.token_estimate == 32
    assert active.status == ConversationSummaryStatus.ACTIVE.value


async def test_upsert_active_supersedes_previous_summary(
    db: aiosqlite.Connection,
    repo: ConversationSummaryRepo,
) -> None:
    await _insert_session(db, "session-summary-2", "buyer-2")

    first = await repo.upsert_active(
        ConversationSummaryCreate(
            session_id="session-summary-2",
            channel="youzan",
            user_id="buyer-2",
            summary_text="旧摘要",
        )
    )
    second = await repo.upsert_active(
        ConversationSummaryCreate(
            session_id="session-summary-2",
            channel="youzan",
            user_id="buyer-2",
            summary_text="新摘要",
        )
    )

    active = await repo.get_active("session-summary-2")
    summaries = await repo.list_by_session("session-summary-2")
    statuses = {summary.id: summary.status for summary in summaries}

    assert active is not None
    assert active.id == second.id
    assert active.summary_text == "新摘要"
    assert statuses[first.id] == ConversationSummaryStatus.SUPERSEDED.value
    assert statuses[second.id] == ConversationSummaryStatus.ACTIVE.value


async def test_discard_active_hides_summary(
    db: aiosqlite.Connection,
    repo: ConversationSummaryRepo,
) -> None:
    await _insert_session(db, "session-summary-3", "buyer-3")
    summary = await repo.upsert_active(
        ConversationSummaryCreate(
            session_id="session-summary-3",
            channel="youzan",
            user_id="buyer-3",
            summary_text="需要丢弃的摘要",
        )
    )

    changed_count = await repo.discard_active("session-summary-3")
    active = await repo.get_active("session-summary-3")
    summaries = await repo.list_by_session("session-summary-3")

    assert changed_count == 1
    assert active is None
    assert {item.id: item.status for item in summaries}[summary.id] == (
        ConversationSummaryStatus.DISCARDED.value
    )


async def _insert_session(
    db: aiosqlite.Connection,
    session_id: str,
    user_id: str,
) -> None:
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status) VALUES (?, ?, ?, ?)",
        (session_id, "youzan", user_id, "active"),
    )
    await db.commit()
