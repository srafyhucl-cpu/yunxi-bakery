"""小程序客服 API 测试。"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi import HTTPException

from app.api.channels.storefront._user import require_storefront_user_id
from app.api.miniapp_chat import create_miniapp_chat_router
from app.constants.miniapp import MINIAPP_DEMO_USER_ID
from app.constants.storefront import DEFAULT_STOREFRONT_HUMAN_TRANSFER_REASON
from tests.helpers.storefront_auth import storefront_auth_headers


class FakeStorefrontConversationService:
    """记录 API 传入参数，避免测试触发真实客服服务。"""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.listed: list[str] = []
        self.transfer_requests: list[dict[str, str]] = []

    async def send_message(
        self, content: str, *, user_id: str = MINIAPP_DEMO_USER_ID
    ) -> dict[str, Any]:
        if not content.strip():
            raise ValueError("消息内容不能为空")
        self.sent.append({"content": content, "user_id": user_id})
        return {
            "sessionId": f"session-{user_id}",
            "reply": "客服回复",
            "messages": [
                {
                    "id": "m_1",
                    "role": "assistant",
                    "content": "客服回复",
                    "createdAt": "2026-06-17 12:00:00",
                }
            ],
            "status": {
                "sessionId": f"session-{user_id}",
                "status": "active",
                "label": "AI 客服接待中",
                "description": "可继续咨询蛋糕、配送和定制问题。",
                "isHumanHandoff": False,
            },
        }

    async def get_chat_payload(
        self, *, user_id: str = MINIAPP_DEMO_USER_ID
    ) -> dict[str, Any]:
        self.listed.append(user_id)
        return {
            "messages": [
                {
                    "id": "m_1",
                    "role": "assistant",
                    "content": f"history:{user_id}",
                    "createdAt": "2026-06-17 12:00:00",
                }
            ],
            "status": {
                "sessionId": f"session-{user_id}",
                "status": "transfer_pending",
                "label": "正在转接人工客服",
                "description": "我们已通知人工客服，请稍候。",
                "isHumanHandoff": True,
            },
        }

    async def request_human_transfer(
        self,
        reason: str = "",
        *,
        user_id: str = MINIAPP_DEMO_USER_ID,
    ) -> dict[str, Any]:
        normalized_reason = reason.strip() or DEFAULT_STOREFRONT_HUMAN_TRANSFER_REASON
        self.transfer_requests.append({"reason": normalized_reason, "user_id": user_id})
        return {
            "messages": [
                {
                    "id": "m_1",
                    "role": "assistant",
                    "content": "已为您转接人工客服",
                    "createdAt": "2026-06-17 12:00:00",
                }
            ],
            "status": {
                "sessionId": f"session-{user_id}",
                "status": "transfer_pending",
                "label": "正在转接人工客服",
                "description": "我们已通知人工客服，请稍候。",
                "isHumanHandoff": True,
            },
        }


@pytest.fixture
def service() -> FakeStorefrontConversationService:
    return FakeStorefrontConversationService()


@pytest.fixture
def app(service: FakeStorefrontConversationService) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(create_miniapp_chat_router(service))
    return test_app


async def test_miniapp_chat_post_uses_user_header(
    app: FastAPI,
    service: FakeStorefrontConversationService,
) -> None:
    """发送客服消息时应使用小程序用户头做会话隔离。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/chat/messages",
            json={"content": "我想订蛋糕"},
            headers=storefront_auth_headers("wx_user_001"),
        )

    assert response.status_code == 200
    assert response.json()["data"]["reply"] == "客服回复"
    assert service.sent == [{"content": "我想订蛋糕", "user_id": "wx_user_001"}]


async def test_miniapp_chat_get_requires_user_header(
    app: FastAPI,
    service: FakeStorefrontConversationService,
) -> None:
    """未带用户头时应返回未登录错误。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/miniapp/chat/messages")

    assert response.status_code == 401
    assert response.json()["detail"] == "未登录或会话未就绪，请先重新登录"


def test_require_storefront_user_id_rejects_blank_value() -> None:
    """空用户头应直接拒绝。"""
    with pytest.raises(HTTPException) as exc_info:
        require_storefront_user_id("   ")

    assert exc_info.value.status_code == 401


async def test_miniapp_chat_rejects_blank_message(app: FastAPI) -> None:
    """空消息应以 400 返回明确错误。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/chat/messages",
            json={"content": "   "},
            headers=storefront_auth_headers("wx_user_001"),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "消息内容不能为空"


async def test_miniapp_chat_transfer_uses_user_header(
    app: FastAPI,
    service: FakeStorefrontConversationService,
) -> None:
    """主动转人工时应使用小程序用户头做工单隔离。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/chat/transfer",
            json={"reason": "需要人工确认配送"},
            headers=storefront_auth_headers("wx_user_transfer"),
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"]["status"] == "transfer_pending"
    assert data["status"]["isHumanHandoff"] is True
    assert service.transfer_requests == [
        {"reason": "需要人工确认配送", "user_id": "wx_user_transfer"}
    ]


async def test_miniapp_chat_transfer_uses_default_reason(
    app: FastAPI,
    service: FakeStorefrontConversationService,
) -> None:
    """未传原因时后端应统一补默认转人工原因。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/chat/transfer",
            json={},
            headers=storefront_auth_headers("wx_user_transfer"),
        )

    assert response.status_code == 200
    assert service.transfer_requests == [
        {
            "reason": DEFAULT_STOREFRONT_HUMAN_TRANSFER_REASON,
            "user_id": "wx_user_transfer",
        }
    ]
