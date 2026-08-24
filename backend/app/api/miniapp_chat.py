"""小程序客服消息 API 兼容入口。"""

from app.api.channels.storefront.chat import (
    create_storefront_chat_router as create_miniapp_chat_router,
)

__all__ = ["create_miniapp_chat_router"]
