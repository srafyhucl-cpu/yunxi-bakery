import pytest

from app.config import settings
from app.models.transfer import HumanTransfer, TransferStatus
from app.repository.transfer_repo import TransferRepo
from app.service.transfer_manager import TransferManager


class MockTransferRepo(TransferRepo):
    def __init__(self) -> None:
        pass

    async def create(
        self, session_id: str, user_id: str, reason: str = "", summary: str = ""
    ) -> HumanTransfer:
        return HumanTransfer(
            id="test_transfer_001",
            session_id=session_id,
            user_id=user_id,
            reason=reason,
            conversation_summary=summary,
            status=TransferStatus.PENDING,
            created_at="0.0",
            accepted_at="",
            closed_at="",
        )


class CapturingTransferManager(TransferManager):
    def __init__(self, repo: TransferRepo) -> None:
        super().__init__(repo)
        self.notified_messages: list[tuple[str, str, str]] = []

    async def notify_staff_emergency(
        self, session_id: str, last_message: str, user_id: str = ""
    ) -> None:
        self.notified_messages.append((session_id, last_message, user_id))


@pytest.mark.asyncio
async def test_transfer_manager_notifies_with_handoff_note_first() -> None:
    mgr = CapturingTransferManager(MockTransferRepo())

    transfer = await mgr.request_transfer(
        session_id="session-summary",
        user_id="buyer-summary",
        reason="转人工",
        summary="客户诉求：给老人/长辈选蛋糕；建议接手：先致歉。",
    )

    assert transfer.conversation_summary.startswith("客户诉求")
    assert mgr.notified_messages == [
        ("session-summary", transfer.conversation_summary, "buyer-summary")
    ]


@pytest.mark.asyncio
async def test_transfer_notification_uses_customer_name_not_session_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "WECOM_ROBOT_WEBHOOK", "")
    monkeypatch.setattr(settings, "WECOM_CORP_ID", "mock_corp_id")
    monkeypatch.setattr(settings, "WECOM_SECRET", "mock_secret")
    monkeypatch.setattr(settings, "WECOM_STAFF_ID", "mock_staff_id")
    monkeypatch.setattr(settings, "WECOM_AGENT_ID", "1000001")

    from app.service.wecom.client import WeComClient

    async def fake_get_token(*args: object, **kwargs: object) -> str:
        return "mock_wecom_token_999"

    async def fake_get_customer_name(*args: object, **kwargs: object) -> str:
        return "小王微信"

    monkeypatch.setattr(WeComClient, "get_token", fake_get_token)
    monkeypatch.setattr(
        WeComClient, "get_kf_customer_display_name", fake_get_customer_name
    )

    captured_requests: list[dict] = []

    class FakeResponse:
        text = '{"errcode": 0, "errmsg": "ok"}'

    import httpx
    from unittest.mock import AsyncMock, MagicMock

    async def capture_post(url: str, *args: object, **kwargs: object) -> FakeResponse:
        captured_requests.append(
            {
                "url": url,
                "json": kwargs.get("json", {}),
                "params": kwargs.get("params", {}),
            }
        )
        return FakeResponse()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.post = AsyncMock(side_effect=capture_post)
    monkeypatch.setattr(httpx, "AsyncClient", MagicMock(return_value=mock_client))

    mgr = TransferManager(MockTransferRepo())
    await mgr.request_transfer(
        session_id="session-hidden",
        user_id="external-user-001",
        reason="转人工",
        summary="客户诉求：给老人/长辈选蛋糕；建议接手：先致歉。",
    )

    assert len(captured_requests) == 1
    content = captured_requests[0]["json"]["markdown"]["content"]
    assert "小王微信" in content
    assert "客户诉求：给老人/长辈选蛋糕" in content
    assert "session-hidden" not in content


@pytest.mark.asyncio
async def test_resolve_staff_id_uses_kf_servicer_userid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "WECOM_STAFF_ID", "")
    monkeypatch.setattr(settings, "WECOM_KF_SERVICER_USERID", "kf-servicer-001")

    mgr = TransferManager(MockTransferRepo())

    assert await mgr._resolve_staff_id() == "kf-servicer-001"
