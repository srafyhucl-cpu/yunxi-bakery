"""
渠道 Webhook 路由接口抽象。

定义多渠道路由的统一协议，便于新增渠道（抖音、美团等）时统一注册模式。
当前有赞和企微已实现该模式。
"""

from typing import Protocol

from fastapi import APIRouter

from app.service.chat import ChatService


class ChannelRouter(Protocol):
    """渠道 Webhook 路由器协议。

    每个渠道必须提供工厂函数，注入 ChatService 后返回注册好路由的 APIRouter。
    """

    def __call__(self, chat_service: ChatService) -> APIRouter:
        """工厂函数：注入 ChatService 依赖，返回带路由的 APIRouter 实例。"""
        ...


# 已知渠道工厂注册表（渠道名 → 工厂函数）
# 新增渠道时在此注册即可
CHANNEL_ROUTERS: dict[str, type[ChannelRouter]] = {}

# 注册有赞渠道工厂
from app.api.integrations.youzan_webhook import (  # noqa: E402
    create_webhook_router as _youzan_factory,
)

CHANNEL_ROUTERS["youzan"] = _youzan_factory


def register_channel(name: str, factory: type[ChannelRouter]) -> None:
    """注册渠道 Webhook 路由器工厂。"""
    if name in CHANNEL_ROUTERS:
        from app.logger import setup_logger

        setup_logger().warning("渠道 %s 已注册，将被覆盖", name)
    CHANNEL_ROUTERS[name] = factory


def get_channel_router(name: str, chat_service: ChatService) -> APIRouter:
    """根据渠道名获取注册好路由的 APIRouter 实例。"""
    factory = CHANNEL_ROUTERS.get(name)
    if factory is None:
        raise ValueError(f"未注册的渠道: {name}")
    return factory(chat_service)
