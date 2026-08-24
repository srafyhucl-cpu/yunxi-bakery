"""客户机器人 LangChain 模型适配测试。"""

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.service.agents.customer.model import (
    CustomerModelRequest,
    request_customer_model_with_tools,
)
from app.service.llm.constants import LLM_FAILURE_REASON_KEY


class _FakeBoundModel:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.messages: list[Any] | None = None
        self.config: dict[str, Any] | None = None
        self._response = response
        self._error = error

    async def ainvoke(self, messages: list[Any], config: dict[str, Any]) -> Any:
        self.messages = messages
        self.config = config
        if self._error is not None:
            raise self._error
        return self._response


class _FakeChatModel:
    def __init__(self, bound_model: _FakeBoundModel) -> None:
        self.bound_model = bound_model
        self.bound_tools: list[Any] | None = None

    def bind_tools(self, tools: list[Any]) -> _FakeBoundModel:
        self.bound_tools = tools
        return self.bound_model


async def _fake_alerter(message: str) -> None:
    raise AssertionError(message)


@pytest.mark.asyncio
async def test_customer_model_uses_langchain_messages_and_bound_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.service.agents.customer import model as customer_model

    response = AIMessage(
        content="最终回复", response_metadata={"finish_reason": "stop"}
    )
    bound_model = _FakeBoundModel(response=response)
    chat_model = _FakeChatModel(bound_model)
    captured: dict[str, Any] = {}

    def fake_get_langchain_chat_model(**kwargs: Any) -> _FakeChatModel:
        captured["model_kwargs"] = kwargs
        return chat_model

    monkeypatch.setattr(
        customer_model,
        "get_langchain_chat_model",
        fake_get_langchain_chat_model,
    )
    timing: dict[str, Any] = {}
    tools = [SimpleNamespace(name="search_knowledge")]

    result = await request_customer_model_with_tools(
        CustomerModelRequest(
            messages=[
                SystemMessage(content="系统提示"),
                HumanMessage(content="配送范围"),
            ],
            tools=tools,
            timing=timing,
            first_llm_started_at=1.0,
            has_image=False,
            fallback_reply="fallback",
            failure_alerter=_fake_alerter,
        )
    )

    assert result.message is response
    assert result.finish_reason == "stop"
    assert result.model_name
    assert chat_model.bound_tools == tools
    assert captured["model_kwargs"]["provider"] == "mimo"
    assert bound_model.messages is not None
    assert isinstance(bound_model.messages[0], SystemMessage)
    assert isinstance(bound_model.messages[1], HumanMessage)
    assert bound_model.config is not None
    assert bound_model.config["run_name"] == "customer_model_with_tools"
    assert bound_model.config["tags"] == ["customer", "model"]
    assert bound_model.config["metadata"]["tool_count"] == 1
    assert set(bound_model.config["metadata"]) == {
        "agent_local_trace_enabled",
        "langsmith_enabled",
        "langchain_project",
        "has_image",
        "tool_count",
    }
    sensitive_metadata_keys = {
        "LANGSMITH_API_KEY",
        "api_key",
        "messages",
        "history_text",
        "customer_profile",
        "tool_result",
    }
    assert sensitive_metadata_keys.isdisjoint(bound_model.config["metadata"])
    assert isinstance(timing["llm_ms"], int)


@pytest.mark.asyncio
async def test_customer_model_marks_tool_calls_without_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.service.agents.customer import model as customer_model

    response = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "tool-1",
                "name": "search_knowledge",
                "args": {"query": "配送"},
                "type": "tool_call",
            }
        ],
    )
    chat_model = _FakeChatModel(_FakeBoundModel(response=response))

    monkeypatch.setattr(
        customer_model,
        "get_langchain_chat_model",
        lambda **_: chat_model,
    )

    result = await request_customer_model_with_tools(
        CustomerModelRequest(
            messages=[HumanMessage(content="配送")],
            tools=[],
            timing={},
            first_llm_started_at=None,
            has_image=False,
            fallback_reply="fallback",
            failure_alerter=_fake_alerter,
        )
    )

    assert result.finish_reason == "tool_calls"
    assert result.message.tool_calls[0]["name"] == "search_knowledge"


@pytest.mark.asyncio
async def test_customer_model_uses_vision_model_when_image_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.service.agents.customer import model as customer_model

    captured: dict[str, Any] = {}
    chat_model = _FakeChatModel(_FakeBoundModel(response=AIMessage(content="ok")))

    def fake_get_langchain_chat_model(**kwargs: Any) -> _FakeChatModel:
        captured.update(kwargs)
        return chat_model

    monkeypatch.setattr(customer_model.settings, "MIMO_VISION_MODEL", "vision-model")
    monkeypatch.setattr(
        customer_model,
        "get_langchain_chat_model",
        fake_get_langchain_chat_model,
    )

    result = await request_customer_model_with_tools(
        CustomerModelRequest(
            messages=[HumanMessage(content="看图")],
            tools=[],
            timing={},
            first_llm_started_at=None,
            has_image=True,
            fallback_reply="fallback",
            failure_alerter=_fake_alerter,
        )
    )

    assert captured["model"] == "vision-model"
    assert result.model_name == "vision-model"


@pytest.mark.asyncio
async def test_customer_model_returns_fallback_on_langchain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.service.agents.customer import model as customer_model

    alerts: list[str] = []
    chat_model = _FakeChatModel(_FakeBoundModel(error=RuntimeError("boom")))

    async def fake_alerter(message: str) -> None:
        alerts.append(message)

    monkeypatch.setattr(
        customer_model,
        "get_langchain_chat_model",
        lambda **_: chat_model,
    )
    timing: dict[str, Any] = {}

    result = await request_customer_model_with_tools(
        CustomerModelRequest(
            messages=[HumanMessage(content="hello")],
            tools=[],
            timing=timing,
            first_llm_started_at=1.0,
            has_image=False,
            fallback_reply="fallback",
            failure_alerter=fake_alerter,
        )
    )

    assert result.message is None
    assert result.fallback_reply == "fallback"
    assert result.finish_reason == "fallback"
    assert result.model_name
    assert timing[LLM_FAILURE_REASON_KEY] == "llm_api_error"
    assert alerts == ["LLMError: customer graph 返回兜底回复"]
