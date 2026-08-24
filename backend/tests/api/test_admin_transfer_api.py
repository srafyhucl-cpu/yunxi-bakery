"""后台转人工 API 测试。"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.api.admin_transfer import create_transfer_router
from app.config import settings


class FakeTransferManager:
    """提供后台转人工路由所需的最小工单能力。"""

    async def get_pending(self) -> list[Any]:
        return []

    async def accept_transfer(self, transfer_id: str, staff_id: str = "") -> None:
        return None

    async def close_transfer(self, transfer_id: str) -> None:
        return None


class FakeAdminService:
    """提供会话消息查询。"""

    async def get_by_session(self, session_id: str) -> list[Any]:
        return [
            type(
                "Message",
                (),
                {
                    "role": "assistant",
                    "content": "人工客服已接手",
                    "created_at": "2026-06-17 12:00:00",
                },
            )()
        ]


class FakeChatService:
    """记录人工回复调用。"""

    def __init__(self) -> None:
        self.replies: list[dict[str, str]] = []

    async def handle_human_reply(self, session_id: str, content: str) -> None:
        self.replies.append({"session_id": session_id, "content": content})


@pytest.fixture
def chat_service() -> FakeChatService:
    return FakeChatService()


@pytest.fixture
def app(chat_service: FakeChatService) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(
        create_transfer_router(
            transfer_mgr=FakeTransferManager(),
            admin_service=FakeAdminService(),
            chat_service=chat_service,
        )
    )
    return test_app


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}


async def test_admin_human_reply_saves_content(
    app: FastAPI,
    chat_service: FakeChatService,
) -> None:
    """后台人工回复接口应把内容交给 ChatService 写入当前会话。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/admin/sessions/session-1/reply",
            params={"content": "人工客服已接手"},
            headers=auth_headers(),
        )

    assert response.status_code == 200
    assert response.json() == {"code": 0, "message": "已发送"}
    assert chat_service.replies == [
        {"session_id": "session-1", "content": "人工客服已接手"}
    ]


async def test_admin_human_reply_rejects_blank_content(app: FastAPI) -> None:
    """空人工回复应被拒绝，避免写入不可见消息。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/admin/sessions/session-1/reply",
            params={"content": "   "},
            headers=auth_headers(),
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "回复内容不能为空"


async def test_admin_session_messages_returns_assistant_reply(app: FastAPI) -> None:
    """后台会话消息接口应返回人工回复内容，供详情抽屉刷新展示。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/admin/sessions/session-1/messages",
            headers=auth_headers(),
        )

    assert response.status_code == 200
    assert response.json()["data"] == [
        {
            "role": "assistant",
            "content": "人工客服已接手",
            "created_at": "2026-06-17 12:00:00",
        }
    ]
