"""企微智能机器人 API 模式消息分发。"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.logger import setup_logger
from app.service.wecom.intelligent_bot_messages import extract_message_text
from app.service.wecom.employee_authorization import EmployeeActorAuthorizer

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

DEFAULT_TOOL_LIMIT = 5
FALLBACK_REPLY = (
    "我现在先支持文本查询。你可以问商品库存、订单、配送售后、待人工或系统状态。"
)
NO_RESULT_REPLY = "工具已执行，但没有返回可读结果，请到后台核对。"
REPLY_TYPE_STREAM = "stream"

logger = setup_logger()


@dataclass(frozen=True)
class WeComBotSkillRoute:
    """API 模式内部 skill 路由。"""

    name: str
    handler: ToolHandler


class WeComBotMessageDispatcher:
    """把企微消息路由到现有只读业务工具。"""

    def __init__(
        self,
        *,
        business_tool_service: Any,
        ops_tool_service: Any,
        status_tool_service: Any,
        employee_agent_service: Any = None,
        actor_authorizer: EmployeeActorAuthorizer | None = None,
    ) -> None:
        self._business_tool_service = business_tool_service
        self._ops_tool_service = ops_tool_service
        self._status_tool_service = status_tool_service
        self._employee_agent_service = employee_agent_service
        self._actor_authorizer = actor_authorizer

    async def dispatch_message(self, message: dict[str, Any]) -> str:
        """处理企微消息回调并返回可发送文本。"""
        authorizer = self._actor_authorizer
        actor = authorizer.authorize(message) if authorizer is not None else None
        text = extract_message_text(message)
        if not text:
            _log_dispatch_result(
                message=message,
                route_name="fallback_no_text",
                reply_text=FALLBACK_REPLY,
                has_text=False,
            )
            return FALLBACK_REPLY
        if self._employee_agent_service is not None:
            allowed_tools = (
                authorizer.allowed_agent_tools(actor)
                if actor is not None and authorizer is not None
                else None
            )
            reply_text = str(
                await self._employee_agent_service.answer(
                    text,
                    allowed_tools=allowed_tools,
                )
            )
            _log_dispatch_result(
                message=message,
                route_name="employee_agent",
                reply_text=reply_text,
                has_text=True,
            )
            return reply_text
        route = self._select_route(text)
        if actor is not None and authorizer is not None:
            authorizer.authorize_tool(actor, route.name)
        payload = _build_tool_payload(text, route.name)
        tool_response = await route.handler(payload)
        reply_text = _extract_reply_text(tool_response)
        _log_dispatch_result(
            message=message,
            route_name=route.name,
            reply_text=reply_text,
            has_text=True,
        )
        return reply_text

    def _select_route(self, text: str) -> WeComBotSkillRoute:
        if _contains_any(text, "待人工", "转人工", "人工处理", "待接单"):
            return WeComBotSkillRoute(
                "handoff_pending", self._ops_tool_service.list_pending_handoffs
            )
        if _contains_any(text, "同步失败", "webhook", "回调失败", "接口失败"):
            return WeComBotSkillRoute(
                "integration_status",
                self._status_tool_service.summarize_integrations,
            )
        if _contains_any(text, "离线复盘", "昨晚复盘", "夜间复盘"):
            return WeComBotSkillRoute(
                "offline_review_summary",
                self._status_tool_service.summarize_offline_review,
            )
        if _contains_any(text, "系统状态", "值守状态", "观察台", "运营状态"):
            return WeComBotSkillRoute(
                "ops_summary", self._status_tool_service.summarize_ops
            )
        if _has_campaign_id(text):
            return WeComBotSkillRoute(
                "group_campaign_summary",
                self._ops_tool_service.summarize_group_campaign,
            )
        if _contains_any(text, "客户", "地址线索", "收货地址"):
            return WeComBotSkillRoute(
                "customer_lookup", self._ops_tool_service.lookup_customer
            )
        if _contains_any(text, "订单", "订单号", "下单记录"):
            return WeComBotSkillRoute(
                "order_lookup", self._business_tool_service.lookup_orders
            )
        if _contains_any(text, "库存", "价格", "商品", "蛋糕", "面包", "甜品"):
            return WeComBotSkillRoute(
                "product_lookup", self._business_tool_service.lookup_products
            )
        return WeComBotSkillRoute(
            "knowledge_answer", self._business_tool_service.answer_knowledge
        )


def _build_tool_payload(text: str, route_name: str) -> dict[str, Any]:
    if route_name == "group_campaign_summary":
        return {"campaignId": _extract_campaign_id(text), "limit": DEFAULT_TOOL_LIMIT}
    if route_name == "knowledge_answer":
        return {"question": text, "limit": DEFAULT_TOOL_LIMIT}
    return {"query": text, "limit": DEFAULT_TOOL_LIMIT}


def _extract_reply_text(tool_response: dict[str, Any]) -> str:
    for key in ("result", "resultText", "suggestedReply", "summary"):
        value = tool_response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return NO_RESULT_REPLY


def _contains_any(text: str, *keywords: str) -> bool:
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in keywords)


def _has_campaign_id(text: str) -> bool:
    return bool(_extract_campaign_id(text))


def _extract_campaign_id(text: str) -> str:
    match = re.search(r"campaign(?:Id|ID|id)?[:：=\s]+([A-Za-z0-9_-]+)", text)
    return match.group(1) if match else ""


def _log_dispatch_result(
    *,
    message: dict[str, Any],
    route_name: str,
    reply_text: str,
    has_text: bool,
) -> None:
    logger.info(
        "企微智能机器人消息已处理 msgtype=%s chattype=%s route=%s reply_type=%s "
        "reply_chars=%d has_text=%s",
        str(message.get("msgtype") or ""),
        str(message.get("chattype") or ""),
        route_name,
        REPLY_TYPE_STREAM,
        len(reply_text),
        has_text,
    )
