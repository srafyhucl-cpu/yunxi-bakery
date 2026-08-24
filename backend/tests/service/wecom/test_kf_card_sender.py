"""微信客服商品卡片安全下载合同测试。"""

from unittest.mock import AsyncMock

import pytest

from app.service.wecom import kf_card_sender


class _Client:
    def __init__(self) -> None:
        self.upload_kf_temp_media = AsyncMock(return_value="media-1")
        self.send_kf_link = AsyncMock(return_value={"errcode": 0})
        self.send_kf_text = AsyncMock(return_value={"errcode": 0})


@pytest.mark.asyncio
async def test_card_image_uses_unified_safe_fetch(monkeypatch) -> None:
    client = _Client()
    safe_fetch = AsyncMock(return_value=(b"image", "image/jpeg"))
    monkeypatch.setattr(kf_card_sender, "fetch_limited_remote_image", safe_fetch)
    monkeypatch.setattr(
        kf_card_sender.settings, "REMOTE_IMAGE_ALLOWED_HOSTS", "img.example"
    )

    await kf_card_sender.send_kf_card(
        client,
        "external-user",
        {"title": "蛋糕", "src": "https://img.example/cake.jpg"},
    )

    safe_fetch.assert_awaited_once()
    client.upload_kf_temp_media.assert_awaited_once()
    assert client.send_kf_link.await_args.kwargs["thumb_media_id"] == "media-1"


@pytest.mark.asyncio
async def test_card_image_safely_degrades_when_fetch_rejected(monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(
        kf_card_sender, "fetch_limited_remote_image", AsyncMock(return_value=None)
    )

    await kf_card_sender.send_kf_card(
        client,
        "external-user",
        {"title": "蛋糕", "src": "http://127.0.0.1/private"},
    )

    client.upload_kf_temp_media.assert_not_awaited()
    assert client.send_kf_link.await_args.kwargs["thumb_media_id"] == ""
