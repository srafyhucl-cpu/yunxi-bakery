"""小程序客服消息兼容入口。"""

from app.service.conversation.storefront import (
    CHAT_STATUS_DESCRIPTIONS,
    CHAT_STATUS_LABELS,
    DEFAULT_CHAT_MESSAGE_LIMIT,
    STOREFRONT_CHAT_CHANNEL,
    StorefrontConversationService as MiniappChatService,
)

MINIAPP_CHAT_CHANNEL = STOREFRONT_CHAT_CHANNEL

__all__ = [
    "CHAT_STATUS_DESCRIPTIONS",
    "CHAT_STATUS_LABELS",
    "DEFAULT_CHAT_MESSAGE_LIMIT",
    "MINIAPP_CHAT_CHANNEL",
    "MiniappChatService",
]
