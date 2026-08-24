"""客户会话摘要只读加载测试。"""

from types import SimpleNamespace

import pytest

from app.service.conversation_summary_memory import (
    load_active_conversation_summary_text,
)


class _FakeSummaryRepo:
    def __init__(self, summary: object | None = None, error: Exception | None = None):
        self.summary = summary
        self.error = error
        self.calls: list[str] = []

    async def get_active(self, session_id: str) -> object | None:
        self.calls.append(session_id)
        if self.error is not None:
            raise self.error
        return self.summary


@pytest.mark.asyncio
async def test_load_active_conversation_summary_returns_empty_without_repo() -> None:
    assert await load_active_conversation_summary_text(None, "session-1") == ""


@pytest.mark.asyncio
async def test_load_active_conversation_summary_returns_empty_without_active() -> None:
    repo = _FakeSummaryRepo()

    result = await load_active_conversation_summary_text(repo, "session-1")

    assert result == ""
    assert repo.calls == ["session-1"]


@pytest.mark.asyncio
async def test_load_active_conversation_summary_trims_text() -> None:
    repo = _FakeSummaryRepo(SimpleNamespace(summary_text="  摘要内容  "))

    result = await load_active_conversation_summary_text(repo, "session-1")

    assert result == "摘要内容"


@pytest.mark.asyncio
async def test_load_active_conversation_summary_falls_back_on_error() -> None:
    repo = _FakeSummaryRepo(error=RuntimeError("boom"))

    result = await load_active_conversation_summary_text(repo, "session-1")

    assert result == ""
