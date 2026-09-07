"""微信客服商品卡片安全下载与统一投递合同测试。"""

from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.database import close_db, db_session_scope, init_db
from app.repository.wecom_kf_outbound_repo import WecomKfOutboundRepo
from app.service.wecom import kf_card_sender
from app.service.wecom.kf_outbound_sender import build_outbound_key


class _Client:
    def __init__(self) -> None:
        self.upload_kf_temp_media = AsyncMock(return_value="media-1")
        self.send_kf_link = AsyncMock(return_value={"errcode": 0})
        self.send_kf_text = AsyncMock(return_value={"errcode": 0})


@pytest.fixture
async def card_db(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """每个用例独享文件数据库，支撑投递账本。"""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "kf-card.db"))
    connection = await init_db(settings.DB_PATH)
    await close_db(connection)
    yield


@pytest.mark.asyncio
async def test_card_image_uses_unified_safe_fetch(card_db, monkeypatch) -> None:
    client = _Client()
    safe_fetch = AsyncMock(return_value=(b"image", "image/jpeg"))
    monkeypatch.setattr(kf_card_sender, "fetch_limited_remote_image", safe_fetch)
    monkeypatch.setattr(
        kf_card_sender.settings, "REMOTE_IMAGE_ALLOWED_HOSTS", "img.example"
    )

    status = await kf_card_sender.send_kf_card(
        client,
        "external-user",
        {"title": "蛋糕", "src": "https://img.example/cake.jpg"},
        db=True,
        inbound_msg_id="card-in-1",
    )

    assert status == "sent"
    safe_fetch.assert_awaited_once()
    client.upload_kf_temp_media.assert_awaited_once()
    assert client.send_kf_link.await_args.kwargs["thumb_media_id"] == "media-1"
    assert client.send_kf_link.await_args.kwargs["msgid"] == build_outbound_key(
        "card-in-1", "card"
    )
    async with db_session_scope():
        row = await WecomKfOutboundRepo().get(build_outbound_key("card-in-1", "card"))
        assert row is not None and row["status"] == "sent"


@pytest.mark.asyncio
async def test_card_image_safely_degrades_when_fetch_rejected(
    card_db, monkeypatch
) -> None:
    client = _Client()
    monkeypatch.setattr(
        kf_card_sender, "fetch_limited_remote_image", AsyncMock(return_value=None)
    )

    status = await kf_card_sender.send_kf_card(
        client,
        "external-user",
        {"title": "蛋糕", "src": "http://127.0.0.1/private"},
        db=True,
        inbound_msg_id="card-in-2",
    )

    assert status == "sent"
    client.upload_kf_temp_media.assert_not_awaited()
    assert client.send_kf_link.await_args.kwargs["thumb_media_id"] == ""


@pytest.mark.asyncio
async def test_card_send_without_inbound_context_rejected(card_db) -> None:
    """缺少投递上下文直接拒绝，不再兼容直发。"""
    client = _Client()
    with pytest.raises(ValueError, match="入站幂等标识"):
        await kf_card_sender.send_kf_card(client, "external-user", {"title": "蛋糕"})
    client.send_kf_link.assert_not_awaited()
    client.send_kf_text.assert_not_awaited()
