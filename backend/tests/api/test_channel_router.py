from __future__ import annotations

import pytest
from fastapi import APIRouter

from app.api import channel_router


def test_get_registered_channel_router_returns_router(monkeypatch) -> None:
    router = APIRouter()

    def fake_factory(chat_service):
        assert chat_service == "chat-service"
        return router

    monkeypatch.setitem(channel_router.CHANNEL_ROUTERS, "test", fake_factory)

    assert channel_router.get_channel_router("test", "chat-service") is router


def test_register_channel_overwrites_existing_factory(monkeypatch) -> None:
    new_router = APIRouter()

    def old_factory(chat_service):
        return APIRouter()

    def new_factory(chat_service):
        return new_router

    monkeypatch.setitem(channel_router.CHANNEL_ROUTERS, "dup", old_factory)

    channel_router.register_channel("dup", new_factory)

    assert channel_router.get_channel_router("dup", object()) is new_router


def test_get_channel_router_rejects_unknown_channel(monkeypatch) -> None:
    monkeypatch.delitem(channel_router.CHANNEL_ROUTERS, "missing", raising=False)

    with pytest.raises(ValueError, match="missing"):
        channel_router.get_channel_router("missing", object())
