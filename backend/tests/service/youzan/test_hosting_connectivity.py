"""有赞客服托管收发连通性测试。"""

import pytest

from app.service.chat import ChatService
from app.service.youzan.client import YouzanClient


class _FakeYouzanClient:
    def __init__(self) -> None:
        self.hosting_replies: list[dict] = []

    async def send_hosting_reply(
        self, conversation_id: str, content: str, msg_type: str = "text"
    ) -> dict:
        self.hosting_replies.append(
            {
                "conversation_id": conversation_id,
                "content": content,
                "msg_type": msg_type,
            }
        )
        return {"response": {"success": True}}


@pytest.mark.asyncio
async def test_chat_service_replies_to_youzan_hosting_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    youzan_client = _FakeYouzanClient()
    service = ChatService(
        session_repo=object(),
        message_repo=object(),
        transfer_repo=object(),
        knowledge_retriever=object(),
        youzan_client=youzan_client,
        youzan_webhook_events_repo=object(),
        youzan_event_handler=object(),
        analytics_repo=object(),
    )
    captured: dict[str, str] = {}

    async def fake_handle_message(
        channel: str,
        user_id: str,
        content: str,
        staff_id: str = "",
        channel_msg_id: str = "",
        image_base64: str | None = None,
    ) -> str:
        captured.update(
            {
                "channel": channel,
                "user_id": user_id,
                "content": content,
                "channel_msg_id": channel_msg_id,
            }
        )
        return "还有现货，可以直接下单。"

    monkeypatch.setattr(service, "handle_message", fake_handle_message)

    await service.handle_youzan_hosting_message(
        conversation_id="conv_abc123",
        yz_open_id="buyer_open_1",
        content="这个蛋糕还有货吗？",
        msg_id="101",
    )

    assert captured == {
        "channel": "youzan",
        "user_id": "buyer_open_1",
        "content": "这个蛋糕还有货吗？",
        "channel_msg_id": "101",
    }
    assert youzan_client.hosting_replies == [
        {
            "conversation_id": "conv_abc123",
            "content": "还有现货，可以直接下单。",
            "msg_type": "text",
        }
    ]


@pytest.mark.asyncio
async def test_youzan_client_uses_hosting_reply_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = YouzanClient()
    captured: dict[str, object] = {}

    async def fake_call(api_name: str, version: str, params: dict) -> dict:
        captured["api_name"] = api_name
        captured["version"] = version
        captured["params"] = params
        return {"response": {"success": True}}

    monkeypatch.setattr(client, "_call", fake_call)

    result = await client.send_hosting_reply(
        conversation_id="conv_abc123",
        content="收到",
    )

    assert result == {"response": {"success": True}}
    assert captured == {
        "api_name": "youzan.message.courier.hosting.operate.replymsg",
        "version": "1.0.0",
        "params": {
            "conversationId": "conv_abc123",
            "msgType": "text",
            "content": "收到",
        },
    }
