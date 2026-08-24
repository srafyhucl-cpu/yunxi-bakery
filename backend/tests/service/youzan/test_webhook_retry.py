"""Concurrency deduplication tests for the Youzan webhook."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from app.api.integrations.youzan_webhook import stop_webhook_dispatchers
from app.api.webhook import create_webhook_router
from app.config import settings
from app.database import close_db, init_db


@pytest.fixture(autouse=True)
async def initialized_webhook_database(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """模拟应用 startup 迁移，并在测试结束回收持久 dispatcher。"""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "webhook.db"))
    connection = await init_db(settings.DB_PATH)
    await close_db(connection)
    yield
    await stop_webhook_dispatchers()


class MockSessionRepo:
    def __init__(self) -> None:
        self._db = None


class MockMessageRepo:
    async def has_processed(self, msg_id: str) -> bool:
        return False


class MockChatService:
    def __init__(self) -> None:
        self._session_repo = MockSessionRepo()
        self._message_repo = MockMessageRepo()
        self.handle_count = 0
        self.hosting_calls: list[dict] = []
        self.system_calls: list[dict] = []
        self.hosting_called = asyncio.Event()

    async def has_processed_message(self, channel_msg_id: str) -> bool:
        return await self._message_repo.has_processed(channel_msg_id)

    async def handle_message_and_reply_youzan(
        self, buyer_id: str, content: str, msg_id: str
    ) -> str:
        self.handle_count += 1
        await asyncio.sleep(0.05)
        return "mock reply"

    async def handle_youzan_hosting_message(
        self,
        conversation_id: str,
        yz_open_id: str,
        content: str,
        msg_id: str,
    ) -> None:
        self.hosting_calls.append(
            {
                "conversation_id": conversation_id,
                "yz_open_id": yz_open_id,
                "content": content,
                "msg_id": msg_id,
            }
        )
        self.hosting_called.set()
        await asyncio.sleep(0.05)

    async def handle_youzan_system_event(
        self,
        payload: dict,
        event_type: str,
        updated_at_str: str,
        msg_id: str,
        audit_id: int | None = None,
    ) -> None:
        self.system_calls.append(
            {
                "payload": payload,
                "event_type": event_type,
                "msg_id": msg_id,
                "audit_id": audit_id,
            }
        )


@pytest.mark.asyncio
async def test_youzan_webhook_concurrency_deduplication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", True)
    monkeypatch.setattr(settings, "YOUZAN_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(settings, "YOUZAN_CLIENT_SECRET", "mock_client_secret")

    from app.api import webhook as webhook_module

    def fake_verify_signature(
        client_id: str, client_secret: str, raw_body: bytes, signature_header: str
    ) -> bool:
        return True

    monkeypatch.setattr(
        webhook_module, "verify_youzan_signature", fake_verify_signature
    )

    chat_service = MockChatService()
    test_app = FastAPI()
    test_app.include_router(create_webhook_router(chat_service))

    payload = {
        "msg_id": "duplicate_msg_id_100200",
        "msg_type": "text",
        "buyer_id": "buyer_999",
        "content": {
            "text": "提拉米苏多少钱",
        },
    }

    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        tasks = [
            client.post(
                "/api/v1/webhook/youzan",
                json=payload,
                headers={"event-sign": "dummy_sig"},
            )
            for _ in range(100)
        ]
        responses = await asyncio.gather(*tasks)

        for response in responses:
            assert response.status_code == 200
            assert response.json() == {"code": 0, "msg": "success"}

        await asyncio.sleep(0.5)

    assert chat_service.handle_count == 1


@pytest.mark.asyncio
async def test_youzan_hosting_message_dispatches_to_hosting_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", True)
    monkeypatch.setattr(settings, "YOUZAN_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(settings, "YOUZAN_CLIENT_SECRET", "mock_client_secret")

    from app.api import webhook as webhook_module

    def fake_verify_signature(
        client_id: str,
        client_secret: str,
        raw_body: bytes,
        signature_header: str,
    ) -> bool:
        return True

    monkeypatch.setattr(
        webhook_module, "verify_youzan_signature", fake_verify_signature
    )

    chat_service = MockChatService()
    test_app = FastAPI()
    test_app.include_router(create_webhook_router(chat_service))

    payload = {
        "id": "push-id-1",
        "type": "youzan_message_CourierHostingMsg",
        "msg": {
            "kdtId": 123456,
            "conversationId": "conv_abc123",
            "msgId": 101,
            "channel": "mmp",
            "msgType": "text",
            "content": "这个蛋糕还有货吗？",
            "yzOpenId": "buyer_open_1",
            "sendTime": 1714776000,
        },
    }

    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/webhook/youzan",
            json=payload,
            headers={"event-sign": "dummy_sig"},
        )

        assert response.status_code == 200
        assert response.json() == {"code": 0, "msg": "success"}
        await asyncio.wait_for(chat_service.hosting_called.wait(), timeout=2)

    assert chat_service.hosting_calls == [
        {
            "conversation_id": "conv_abc123",
            "yz_open_id": "buyer_open_1",
            "content": "这个蛋糕还有货吗？",
            "msg_id": "101",
        }
    ]
    assert chat_service.system_calls == []


@pytest.mark.asyncio
async def test_youzan_hosting_message_deduplicates_by_hosting_msg_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", True)
    monkeypatch.setattr(settings, "YOUZAN_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(settings, "YOUZAN_CLIENT_SECRET", "mock_client_secret")

    from app.api import webhook as webhook_module

    def fake_verify_signature(
        client_id: str,
        client_secret: str,
        raw_body: bytes,
        signature_header: str,
    ) -> bool:
        return True

    monkeypatch.setattr(
        webhook_module, "verify_youzan_signature", fake_verify_signature
    )

    chat_service = MockChatService()
    test_app = FastAPI()
    test_app.include_router(create_webhook_router(chat_service))
    payload = {
        "id": "push-id-2",
        "type": "youzan_message_CourierHostingMsg",
        "msg": {
            "conversationId": "conv_duplicate",
            "msgId": 202,
            "channel": "mmp",
            "msgType": "text",
            "content": "你好",
            "yzOpenId": "buyer_open_2",
        },
    }

    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        responses = await asyncio.gather(
            client.post(
                "/api/v1/webhook/youzan",
                json=payload,
                headers={"event-sign": "dummy_sig"},
            ),
            client.post(
                "/api/v1/webhook/youzan",
                json=payload,
                headers={"event-sign": "dummy_sig"},
            ),
        )
        assert [response.status_code for response in responses] == [200, 200]
        await asyncio.wait_for(chat_service.hosting_called.wait(), timeout=2)
        await asyncio.sleep(0.1)

    assert len(chat_service.hosting_calls) == 1
