from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.service.wecom.intelligent_bot_dispatcher import WeComBotMessageDispatcher


class _FakeBusinessToolService:
    async def lookup_orders(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"result": f"order:{payload['query']}"}

    async def lookup_products(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"result": f"product:{payload['query']}"}

    async def answer_knowledge(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"result": f"knowledge:{payload['question']}"}


class _FakeEmployeeAgentService:
    async def answer(
        self,
        query: str,
        *,
        allowed_tools: frozenset[str] | None = None,
    ) -> str:
        return f"agent:{query}"


async def test_dispatcher_prioritizes_order_intent_over_product_words() -> None:
    dispatcher = WeComBotMessageDispatcher(
        business_tool_service=_FakeBusinessToolService(),
        ops_tool_service=SimpleNamespace(),
        status_tool_service=SimpleNamespace(),
    )

    reply = await dispatcher.dispatch_message(
        {"msgtype": "text", "text": {"content": "查一下草莓蛋糕订单"}}
    )

    assert reply == "order:查一下草莓蛋糕订单"


async def test_dispatcher_uses_employee_agent_when_injected() -> None:
    dispatcher = WeComBotMessageDispatcher(
        business_tool_service=_FakeBusinessToolService(),
        ops_tool_service=SimpleNamespace(),
        status_tool_service=SimpleNamespace(),
        employee_agent_service=_FakeEmployeeAgentService(),
    )

    reply = await dispatcher.dispatch_message(
        {"msgtype": "text", "text": {"content": "今天一共多少订单"}}
    )

    assert reply == "agent:今天一共多少订单"
