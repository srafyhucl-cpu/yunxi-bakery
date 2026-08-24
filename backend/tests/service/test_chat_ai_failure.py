from __future__ import annotations

import json

from app.models.session import Session, SessionStatus
from app.service.chat_ai_failure import (
    AI_FAILURE_AUTO_TRANSFER_EVENT_TYPE,
    AiFailureAutoTransferContext,
    handle_ai_failure_auto_transfer,
)


class _FakeTransferManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    async def request_transfer(
        self,
        session_id: str,
        user_id: str,
        reason: str = "",
        summary: str = "",
    ) -> object:
        self.calls.append(
            {
                "session_id": session_id,
                "user_id": user_id,
                "reason": reason,
                "summary": summary,
            }
        )
        return object()


class _FakeSessionRepo:
    def __init__(self) -> None:
        self.status_updates: list[tuple[str, SessionStatus]] = []
        self.extra_updates: list[tuple[str, str]] = []

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        self.status_updates.append((session_id, status))

    async def update_extra(self, session_id: str, extra_info: str) -> None:
        self.extra_updates.append((session_id, extra_info))


class _FakeAnalyticsRepo:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.events: list[dict[str, object]] = []

    async def add_event(self, **kwargs: object) -> None:
        if self.should_fail:
            raise RuntimeError("analytics unavailable")
        self.events.append(kwargs)


class _FailingTransferManager:
    async def request_transfer(
        self,
        session_id: str,
        user_id: str,
        reason: str = "",
        summary: str = "",
    ) -> object:
        raise RuntimeError("transfer unavailable")


def _build_context(
    *,
    transfer_mgr: object | None = None,
    session_repo: object | None = None,
    analytics_repo: object | None = None,
) -> AiFailureAutoTransferContext:
    return AiFailureAutoTransferContext(
        session=Session(id="session-1", channel="youzan", user_id="buyer-1"),
        user_id="buyer-1",
        channel="youzan",
        history_text="用户：想订生日蛋糕",
        failure_reason="llm_api_error",
        transfer_mgr=transfer_mgr or _FakeTransferManager(),
        session_repo=session_repo or _FakeSessionRepo(),
        analytics_repo=analytics_repo or _FakeAnalyticsRepo(),
        fallback_reply="系统繁忙，请稍后再试",
        auto_transfer_reply="我先为您转人工接手",
    )


async def test_handle_ai_failure_auto_transfer_returns_handoff_reply() -> None:
    transfer_mgr = _FakeTransferManager()
    session_repo = _FakeSessionRepo()
    analytics_repo = _FakeAnalyticsRepo()

    reply = await handle_ai_failure_auto_transfer(
        _build_context(
            transfer_mgr=transfer_mgr,
            session_repo=session_repo,
            analytics_repo=analytics_repo,
        )
    )

    assert reply == "我先为您转人工接手"
    assert transfer_mgr.calls[0]["session_id"] == "session-1"
    assert transfer_mgr.calls[0]["user_id"] == "buyer-1"
    assert "llm_api_error" in transfer_mgr.calls[0]["reason"]
    assert session_repo.status_updates == [
        ("session-1", SessionStatus.TRANSFER_PENDING)
    ]
    assert session_repo.extra_updates
    event = analytics_repo.events[0]
    assert event["event_type"] == AI_FAILURE_AUTO_TRANSFER_EVENT_TYPE
    meta_data = json.loads(str(event["meta_data"]))
    assert meta_data["channel"] == "youzan"
    assert meta_data["failure_reason"] == "llm_api_error"
    assert meta_data["transfer_created"] is True


async def test_handle_ai_failure_auto_transfer_falls_back_when_transfer_fails() -> None:
    analytics_repo = _FakeAnalyticsRepo()

    reply = await handle_ai_failure_auto_transfer(
        _build_context(
            transfer_mgr=_FailingTransferManager(),
            analytics_repo=analytics_repo,
        )
    )

    assert reply == "系统繁忙，请稍后再试"
    meta_data = json.loads(str(analytics_repo.events[0]["meta_data"]))
    assert meta_data["transfer_created"] is False


async def test_handle_ai_failure_auto_transfer_ignores_analytics_failure() -> None:
    reply = await handle_ai_failure_auto_transfer(
        _build_context(analytics_repo=_FakeAnalyticsRepo(should_fail=True))
    )

    assert reply == "我先为您转人工接手"
