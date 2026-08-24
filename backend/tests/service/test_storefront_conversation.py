"""小程序客服服务测试。"""

import aiosqlite

from app.models.message import Message, MessageRole
from app.models.session import SessionCreate, SessionStatus
from app.repository.message_repo import MessageRepo
from app.repository.session_repo import SessionRepo
from app.service.conversation.storefront import (
    DEFAULT_STOREFRONT_HUMAN_TRANSFER_REASON,
    DEFAULT_CHAT_MESSAGE_LIMIT,
    STOREFRONT_CHAT_CHANNEL,
    StorefrontConversationService,
)
from app.constants.storefront import STOREFRONT_CHANNEL_MESSAGE_PREFIX


class FakeTransferManager:
    """记录转人工工单请求，避免测试触发外部通知。"""

    def __init__(self) -> None:
        self.requests: list[dict] = []

    async def request_transfer(
        self,
        session_id: str,
        user_id: str,
        reason: str = "",
        summary: str = "",
    ) -> None:
        self.requests.append(
            {
                "session_id": session_id,
                "user_id": user_id,
                "reason": reason,
                "summary": summary,
            }
        )


class FakeChatService:
    """避免测试触发真实 LLM，只验证小程序客服服务边界。"""

    def __init__(self, session_repo: SessionRepo, message_repo: MessageRepo) -> None:
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.calls: list[dict] = []

    async def handle_message(
        self,
        *,
        channel: str,
        user_id: str,
        content: str,
        channel_msg_id: str,
    ) -> str:
        self.calls.append(
            {
                "channel": channel,
                "user_id": user_id,
                "content": content,
                "channel_msg_id": channel_msg_id,
            }
        )
        session = await self.session_repo.get_or_create(
            SessionCreate(id="", channel=channel, user_id=user_id)
        )
        await self.message_repo.save(
            Message(
                id="",
                session_id=session.id,
                role=MessageRole.USER,
                content=content,
                channel_msg_id=channel_msg_id,
            )
        )
        await self.message_repo.save(
            Message(
                id="",
                session_id=session.id,
                role=MessageRole.ASSISTANT,
                content=f"收到：{content}",
            )
        )
        return f"收到：{content}"


async def test_miniapp_chat_send_message_trims_content_and_returns_history(
    db: aiosqlite.Connection,
) -> None:
    """发送消息时应复用小程序渠道，并返回用户与助手可见消息。"""
    message_repo = MessageRepo(db)
    session_repo = SessionRepo(db)
    fake_chat = FakeChatService(session_repo, message_repo)
    service = StorefrontConversationService(
        chat_service=fake_chat,
        session_repo=session_repo,
        message_repo=message_repo,
        transfer_mgr=FakeTransferManager(),
    )

    result = await service.send_message(
        "  我想订生日蛋糕  ", user_id="miniapp-chat-user"
    )

    assert result["reply"] == "收到：我想订生日蛋糕"
    assert result["sessionId"]
    assert fake_chat.calls[0]["channel"] == STOREFRONT_CHAT_CHANNEL
    assert fake_chat.calls[0]["user_id"] == "miniapp-chat-user"
    assert fake_chat.calls[0]["content"] == "我想订生日蛋糕"
    assert fake_chat.calls[0]["channel_msg_id"].startswith(
        f"{STOREFRONT_CHANNEL_MESSAGE_PREFIX}:miniapp-chat-user:"
    )
    assert [message["role"] for message in result["messages"]] == ["user", "assistant"]
    assert [message["content"] for message in result["messages"]] == [
        "我想订生日蛋糕",
        "收到：我想订生日蛋糕",
    ]


async def test_miniapp_chat_list_messages_creates_session_and_filters_internal_roles(
    db: aiosqlite.Connection,
) -> None:
    """历史拉取应自动建立会话，只返回用户和助手消息。"""
    session_repo = SessionRepo(db)
    message_repo = MessageRepo(db)
    service = StorefrontConversationService(
        chat_service=FakeChatService(session_repo, message_repo),
        session_repo=session_repo,
        message_repo=message_repo,
        transfer_mgr=FakeTransferManager(),
    )
    session = await session_repo.get_or_create(
        SessionCreate(
            id="", channel=STOREFRONT_CHAT_CHANNEL, user_id="miniapp-history-user"
        )
    )
    await message_repo.save(
        Message(
            id="", session_id=session.id, role=MessageRole.SYSTEM, content="内部提示"
        )
    )
    await message_repo.save(
        Message(id="", session_id=session.id, role=MessageRole.USER, content="配送范围")
    )
    await message_repo.save(
        Message(
            id="",
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content="请提供地址",
        )
    )
    await message_repo.save(
        Message(id="", session_id=session.id, role=MessageRole.TOOL, content="工具结果")
    )

    messages = await service.list_messages(user_id="miniapp-history-user")

    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert [message["content"] for message in messages] == ["配送范围", "请提供地址"]


async def test_miniapp_chat_list_messages_uses_stable_limit(
    db: aiosqlite.Connection,
) -> None:
    """历史消息数量上限应集中由服务常量控制。"""
    session_repo = SessionRepo(db)
    message_repo = MessageRepo(db)
    service = StorefrontConversationService(
        chat_service=FakeChatService(session_repo, message_repo),
        session_repo=session_repo,
        message_repo=message_repo,
        transfer_mgr=FakeTransferManager(),
    )
    session = await session_repo.get_or_create(
        SessionCreate(
            id="", channel=STOREFRONT_CHAT_CHANNEL, user_id="miniapp-limit-user"
        )
    )
    for index in range(DEFAULT_CHAT_MESSAGE_LIMIT + 3):
        await message_repo.save(
            Message(
                id="",
                session_id=session.id,
                role=MessageRole.USER,
                content=f"消息 {index}",
            )
        )

    messages = await service.list_messages(user_id="miniapp-limit-user")

    assert len(messages) == DEFAULT_CHAT_MESSAGE_LIMIT
    assert messages[0]["content"] == "消息 3"
    assert messages[-1]["content"] == f"消息 {DEFAULT_CHAT_MESSAGE_LIMIT + 2}"


async def test_miniapp_chat_payload_exposes_handoff_status(
    db: aiosqlite.Connection,
) -> None:
    """小程序客服 payload 应暴露当前 AI/人工接待状态。"""
    session_repo = SessionRepo(db)
    message_repo = MessageRepo(db)
    service = StorefrontConversationService(
        chat_service=FakeChatService(session_repo, message_repo),
        session_repo=session_repo,
        message_repo=message_repo,
        transfer_mgr=FakeTransferManager(),
    )
    session = await session_repo.get_or_create(
        SessionCreate(
            id="", channel=STOREFRONT_CHAT_CHANNEL, user_id="miniapp-handoff-user"
        )
    )
    await session_repo.update_status(session.id, SessionStatus.TRANSFER_PENDING)

    payload = await service.get_chat_payload(user_id="miniapp-handoff-user")

    assert payload["status"] == {
        "sessionId": session.id,
        "status": "transfer_pending",
        "label": "正在转接人工客服",
        "description": "我们已通知人工客服，请稍候。",
        "isHumanHandoff": True,
    }


async def test_miniapp_chat_payload_includes_human_reply_saved_as_assistant(
    db: aiosqlite.Connection,
) -> None:
    """后台人工回复写入会话后，小程序应能在消息列表中刷新看到。"""
    session_repo = SessionRepo(db)
    message_repo = MessageRepo(db)
    service = StorefrontConversationService(
        chat_service=FakeChatService(session_repo, message_repo),
        session_repo=session_repo,
        message_repo=message_repo,
        transfer_mgr=FakeTransferManager(),
    )
    session = await session_repo.get_or_create(
        SessionCreate(
            id="", channel=STOREFRONT_CHAT_CHANNEL, user_id="miniapp-human-reply-user"
        )
    )
    await message_repo.save(
        Message(
            id="",
            session_id=session.id,
            role=MessageRole.USER,
            content="请人工确认配送",
        )
    )
    await message_repo.save(
        Message(
            id="",
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content="人工客服已接手",
        )
    )

    payload = await service.get_chat_payload(user_id="miniapp-human-reply-user")

    assert [message["content"] for message in payload["messages"]] == [
        "请人工确认配送",
        "人工客服已接手",
    ]


async def test_miniapp_chat_request_human_transfer_creates_ticket_and_payload(
    db: aiosqlite.Connection,
    monkeypatch,
) -> None:
    """用户主动转人工应复用现有工单通道，并返回等待接单状态。"""

    async def fake_summary(reason: str, history_text: str) -> str:
        return f"客户诉求：{reason}；最近记录：{history_text[-20:]}"

    monkeypatch.setattr(
        "app.service.chat_transfer.build_transfer_summary",
        fake_summary,
    )
    session_repo = SessionRepo(db)
    message_repo = MessageRepo(db)
    transfer_mgr = FakeTransferManager()
    service = StorefrontConversationService(
        chat_service=FakeChatService(session_repo, message_repo),
        session_repo=session_repo,
        message_repo=message_repo,
        transfer_mgr=transfer_mgr,
    )
    await service.send_message("我想订一个低糖蛋糕", user_id="miniapp-transfer-user")

    payload = await service.request_human_transfer(
        " 想让门店人工确认款式 ",
        user_id="miniapp-transfer-user",
    )

    session = await session_repo.get_active(
        "miniapp-transfer-user",
        STOREFRONT_CHAT_CHANNEL,
    )
    assert session is not None
    assert session.status == SessionStatus.TRANSFER_PENDING
    assert payload["status"]["status"] == "transfer_pending"
    assert payload["status"]["isHumanHandoff"] is True
    assert transfer_mgr.requests[0]["session_id"] == session.id
    assert transfer_mgr.requests[0]["user_id"] == "miniapp-transfer-user"
    assert transfer_mgr.requests[0]["reason"] == "想让门店人工确认款式"
    assert "客户诉求" in transfer_mgr.requests[0]["summary"]


async def test_miniapp_chat_request_human_transfer_uses_default_reason(
    db: aiosqlite.Connection,
    monkeypatch,
) -> None:
    """未填写原因时应使用统一默认文案，避免页面写死业务话术。"""

    async def fake_summary(reason: str, history_text: str) -> str:
        return reason

    monkeypatch.setattr(
        "app.service.chat_transfer.build_transfer_summary",
        fake_summary,
    )
    session_repo = SessionRepo(db)
    message_repo = MessageRepo(db)
    transfer_mgr = FakeTransferManager()
    service = StorefrontConversationService(
        chat_service=FakeChatService(session_repo, message_repo),
        session_repo=session_repo,
        message_repo=message_repo,
        transfer_mgr=transfer_mgr,
    )

    await service.request_human_transfer("   ", user_id="miniapp-transfer-empty-reason")

    assert (
        transfer_mgr.requests[0]["reason"] == DEFAULT_STOREFRONT_HUMAN_TRANSFER_REASON
    )
