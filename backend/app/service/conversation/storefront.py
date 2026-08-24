"""前台客服会话服务。"""

from uuid import uuid4

from app.constants.storefront import (
    DEFAULT_STOREFRONT_HUMAN_TRANSFER_REASON,
    STOREFRONT_CHANNEL,
    STOREFRONT_CHANNEL_MESSAGE_PREFIX,
    STOREFRONT_DEMO_USER_ID,
)
from app.models.session import SessionCreate
from app.repository.message_repo import MessageRepo
from app.repository.session_repo import SessionRepo
from app.service.chat import ChatService
from app.service.chat_transfer import HumanTransferContext, request_human_transfer
from app.service.transfer_manager import TransferManager

STOREFRONT_CHAT_CHANNEL = STOREFRONT_CHANNEL
DEFAULT_CHAT_MESSAGE_LIMIT = 50
CHAT_STATUS_LABELS = {
    "active": "AI 客服接待中",
    "transfer_pending": "正在转接人工客服",
    "human_service": "人工客服接待中",
    "closed": "会话已结束",
}
CHAT_STATUS_DESCRIPTIONS = {
    "active": "可继续咨询蛋糕、配送和定制问题。",
    "transfer_pending": "我们已通知人工客服，请稍候。",
    "human_service": "人工客服正在接待，AI 将暂停自动回复。",
    "closed": "可重新发送消息开启新的咨询。",
}


class StorefrontConversationService:
    """为前台渠道提供客服消息发送与历史拉取。"""

    def __init__(
        self,
        chat_service: ChatService,
        session_repo: SessionRepo,
        message_repo: MessageRepo,
        transfer_mgr: TransferManager,
    ) -> None:
        self._chat_service = chat_service
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._transfer_mgr = transfer_mgr

    async def send_message(
        self, content: str, *, user_id: str = STOREFRONT_DEMO_USER_ID
    ) -> dict:
        """发送一条前台用户消息，并返回 AI 回复。"""
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("消息内容不能为空")
        reply = await self._chat_service.handle_message(
            channel=STOREFRONT_CHAT_CHANNEL,
            user_id=user_id,
            content=normalized_content,
            channel_msg_id=f"{STOREFRONT_CHANNEL_MESSAGE_PREFIX}:{user_id}:{uuid4().hex}",
        )
        session = await self._session_repo.get_active(user_id, STOREFRONT_CHAT_CHANNEL)
        return {
            "sessionId": session.id if session else "",
            "reply": reply or "",
            "messages": await self.list_messages(user_id=user_id),
            "status": await self.get_chat_status(user_id=user_id),
        }

    async def get_chat_payload(self, *, user_id: str = STOREFRONT_DEMO_USER_ID) -> dict:
        """返回前台客服页所需的消息和会话状态。"""
        return {
            "messages": await self.list_messages(user_id=user_id),
            "status": await self.get_chat_status(user_id=user_id),
        }

    async def request_human_transfer(
        self,
        reason: str = "",
        *,
        user_id: str = STOREFRONT_DEMO_USER_ID,
    ) -> dict:
        """为前台用户主动创建转人工工单，并返回最新客服页 payload。"""
        normalized_reason = reason.strip() or DEFAULT_STOREFRONT_HUMAN_TRANSFER_REASON
        session = await self._session_repo.get_or_create(
            SessionCreate(id="", channel=STOREFRONT_CHAT_CHANNEL, user_id=user_id)
        )
        visible_messages = await self.list_messages(user_id=user_id)
        history_text = "\n".join(
            f"{self._history_role_label(message['role'])}：{message['content']}"
            for message in visible_messages
        )
        created = await request_human_transfer(
            HumanTransferContext(
                session=session,
                user_id=user_id,
                reason=normalized_reason,
                history_text=history_text,
                transfer_mgr=self._transfer_mgr,
                session_repo=self._session_repo,
            )
        )
        if not created:
            raise ValueError("转人工请求失败，请稍后重试")
        return await self.get_chat_payload(user_id=user_id)

    async def get_chat_status(self, *, user_id: str = STOREFRONT_DEMO_USER_ID) -> dict:
        """读取当前前台客服会话状态。"""
        session = await self._session_repo.get_active(user_id, STOREFRONT_CHAT_CHANNEL)
        status = self._normalize_session_status(session.status if session else "active")
        return {
            "sessionId": session.id if session else "",
            "status": status,
            "label": CHAT_STATUS_LABELS[status],
            "description": CHAT_STATUS_DESCRIPTIONS[status],
            "isHumanHandoff": status in {"transfer_pending", "human_service"},
        }

    async def list_messages(
        self, *, user_id: str = STOREFRONT_DEMO_USER_ID
    ) -> list[dict]:
        """读取当前前台用户客服消息。"""
        session = await self._session_repo.get_active(user_id, STOREFRONT_CHAT_CHANNEL)
        if session is None:
            session = await self._session_repo.get_or_create(
                SessionCreate(id="", channel=STOREFRONT_CHAT_CHANNEL, user_id=user_id)
            )
        messages = await self._message_repo.get_by_session(
            session.id,
            limit=DEFAULT_CHAT_MESSAGE_LIMIT,
        )
        return [
            {
                "id": message.id,
                "role": message.role.value
                if hasattr(message.role, "value")
                else str(message.role),
                "content": message.content,
                "createdAt": message.created_at,
            }
            for message in messages
            if self._is_visible_role(message.role)
        ]

    def _is_visible_role(self, role: object) -> bool:
        role_value = role.value if hasattr(role, "value") else str(role)
        return role_value in {"user", "assistant"}

    def _normalize_session_status(self, status: object) -> str:
        status_value = status.value if hasattr(status, "value") else str(status)
        return status_value if status_value in CHAT_STATUS_LABELS else "active"

    def _history_role_label(self, role: object) -> str:
        role_value = role.value if hasattr(role, "value") else str(role)
        return "用户" if role_value == "user" else "AI"


__all__ = [
    "CHAT_STATUS_DESCRIPTIONS",
    "CHAT_STATUS_LABELS",
    "DEFAULT_CHAT_MESSAGE_LIMIT",
    "STOREFRONT_CHAT_CHANNEL",
    "DEFAULT_STOREFRONT_HUMAN_TRANSFER_REASON",
    "StorefrontConversationService",
]
