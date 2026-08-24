"""客户会话摘要回复后调度测试。"""

import pytest

from app.models.conversation_summary import (
    ConversationSummary,
    ConversationSummaryCreate,
)
from app.models.message import Message, MessageRole
from app.models.session import Session, SessionStatus
from app.service.conversation_summary_scheduler import (
    ConversationSummaryAfterReplyRequest,
    run_conversation_summary_after_reply,
)
from app.service.conversation_summary_service import (
    ConversationSummaryGenerationRequest,
)


class _FakeMessageRepo:
    def __init__(self, messages: list[Message]) -> None:
        self.messages = messages
        self.calls: list[tuple[str, int]] = []

    async def get_by_session(self, session_id: str, limit: int = 50) -> list[Message]:
        self.calls.append((session_id, limit))
        return self.messages


class _FakeSummaryRepo:
    def __init__(
        self,
        active_summary: ConversationSummary | None = None,
        should_fail: bool = False,
    ) -> None:
        self.active_summary = active_summary
        self.should_fail = should_fail
        self.saved: list[ConversationSummaryCreate] = []

    async def get_active(self, session_id: str) -> ConversationSummary | None:
        if self.should_fail:
            raise RuntimeError("repo failed")
        return self.active_summary

    async def upsert_active(
        self, summary: ConversationSummaryCreate
    ) -> ConversationSummaryCreate:
        self.saved.append(summary)
        return summary


@pytest.mark.asyncio
async def test_run_conversation_summary_after_reply_skips_non_candidate() -> None:
    message_repo = _FakeMessageRepo([_message("msg-1", MessageRole.USER, "你好")])
    summary_repo = _FakeSummaryRepo()
    generated: list[ConversationSummaryGenerationRequest] = []

    async def fake_generator(
        request: ConversationSummaryGenerationRequest,
    ) -> ConversationSummaryCreate | None:
        generated.append(request)
        return _draft(request)

    saved = await run_conversation_summary_after_reply(
        _request({"needs_session_summary_candidate": False}),
        message_repo,
        summary_repo,
        fake_generator,
    )

    assert saved is False
    assert message_repo.calls == []
    assert generated == []
    assert summary_repo.saved == []


@pytest.mark.asyncio
async def test_run_conversation_summary_after_reply_saves_generated_draft() -> None:
    message_repo = _FakeMessageRepo(
        [
            _message("msg-1", MessageRole.USER, "想订低糖蛋糕"),
            _message("msg-2", MessageRole.ASSISTANT, "需要确认配送时间"),
        ]
    )
    summary_repo = _FakeSummaryRepo(_summary(source_until_message_id="old-msg"))
    generated: list[ConversationSummaryGenerationRequest] = []

    async def fake_generator(
        request: ConversationSummaryGenerationRequest,
    ) -> ConversationSummaryCreate | None:
        generated.append(request)
        return _draft(request)

    saved = await run_conversation_summary_after_reply(
        _request({"needs_session_summary_candidate": True}),
        message_repo,
        summary_repo,
        fake_generator,
    )

    assert saved is True
    assert generated[0].existing_summary_text == "旧摘要"
    assert generated[0].messages == message_repo.messages
    assert summary_repo.saved[0].summary_text == "客户想订低糖蛋糕。"


@pytest.mark.asyncio
async def test_run_conversation_summary_after_reply_skips_fresh_active_summary() -> (
    None
):
    message_repo = _FakeMessageRepo(
        [
            _message("msg-1", MessageRole.USER, "第一句"),
            _message("msg-2", MessageRole.ASSISTANT, "第二句"),
            _message("msg-3", MessageRole.USER, "第三句"),
        ]
    )
    summary_repo = _FakeSummaryRepo(_summary(source_until_message_id="msg-2"))

    async def fake_generator(
        request: ConversationSummaryGenerationRequest,
    ) -> ConversationSummaryCreate | None:
        raise AssertionError("摘要仍新鲜时不应调用生成器")

    saved = await run_conversation_summary_after_reply(
        _request({"needs_session_summary_candidate": True}),
        message_repo,
        summary_repo,
        fake_generator,
    )

    assert saved is False
    assert summary_repo.saved == []


@pytest.mark.asyncio
async def test_run_conversation_summary_after_reply_skips_human_service() -> None:
    message_repo = _FakeMessageRepo([_message("msg-1", MessageRole.USER, "你好")])
    summary_repo = _FakeSummaryRepo()

    async def fake_generator(
        request: ConversationSummaryGenerationRequest,
    ) -> ConversationSummaryCreate | None:
        raise AssertionError("人工服务中不应调用生成器")

    saved = await run_conversation_summary_after_reply(
        _request(
            {"needs_session_summary_candidate": True},
            status=SessionStatus.HUMAN_SERVICE,
        ),
        message_repo,
        summary_repo,
        fake_generator,
    )

    assert saved is False
    assert message_repo.calls == []


@pytest.mark.asyncio
async def test_run_conversation_summary_after_reply_discards_empty_draft() -> None:
    message_repo = _FakeMessageRepo([_message("msg-1", MessageRole.USER, "你好")])
    summary_repo = _FakeSummaryRepo()

    async def fake_generator(
        request: ConversationSummaryGenerationRequest,
    ) -> ConversationSummaryCreate | None:
        return None

    saved = await run_conversation_summary_after_reply(
        _request({"needs_session_summary_candidate": True}),
        message_repo,
        summary_repo,
        fake_generator,
    )

    assert saved is False
    assert summary_repo.saved == []


@pytest.mark.asyncio
async def test_run_conversation_summary_after_reply_catches_repo_error() -> None:
    message_repo = _FakeMessageRepo([_message("msg-1", MessageRole.USER, "你好")])
    summary_repo = _FakeSummaryRepo(should_fail=True)

    async def fake_generator(
        request: ConversationSummaryGenerationRequest,
    ) -> ConversationSummaryCreate | None:
        raise AssertionError("仓库失败后不应继续生成")

    saved = await run_conversation_summary_after_reply(
        _request({"needs_session_summary_candidate": True}),
        message_repo,
        summary_repo,
        fake_generator,
    )

    assert saved is False


def _request(
    context_budget: dict[str, object],
    status: SessionStatus = SessionStatus.ACTIVE,
) -> ConversationSummaryAfterReplyRequest:
    return ConversationSummaryAfterReplyRequest(
        session=Session(
            id="session-1",
            channel="youzan",
            user_id="buyer-1",
            status=status,
        ),
        context_budget=context_budget,
    )


def _message(message_id: str, role: MessageRole, content: str) -> Message:
    return Message(
        id=message_id,
        session_id="session-1",
        role=role,
        content=content,
    )


def _summary(source_until_message_id: str) -> ConversationSummary:
    return ConversationSummary(
        id="summary-1",
        session_id="session-1",
        channel="youzan",
        user_id="buyer-1",
        summary_text="旧摘要",
        source_until_message_id=source_until_message_id,
    )


def _draft(
    request: ConversationSummaryGenerationRequest,
) -> ConversationSummaryCreate:
    return ConversationSummaryCreate(
        session_id=request.session_id,
        channel=request.channel,
        user_id=request.user_id,
        summary_text="客户想订低糖蛋糕。",
        source_until_message_id="msg-2",
    )
