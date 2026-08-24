"""客户会话短期摘要生成服务测试。"""

import json

import pytest
from langchain_core.runnables import RunnableLambda

from app.exceptions import LLMError
from app.models.message import Message, MessageRole
from app.service import conversation_summary_service as summary_module
from app.service.conversation_summary_service import (
    ConversationSummaryGenerationRequest,
    generate_conversation_summary_draft,
)


@pytest.mark.asyncio
async def test_generate_conversation_summary_draft_parses_safe_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_messages: list[dict] = []

    async def fake_summary_chain(
        messages: list[Message], existing_summary_text: str
    ) -> str:
        captured_messages.extend(
            summary_module._build_summary_messages(messages, existing_summary_text)
        )
        return json.dumps(
            {
                "customer_goal": "想确认生日蛋糕配送",
                "confirmed_facts": ["偏好低糖"],
                "pending_questions": ["配送时间待确认"],
                "service_boundaries": ["库存和配送需以工具查询为准"],
                "handoff_state": "none",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(summary_module, "_invoke_summary_chain", fake_summary_chain)

    draft = await generate_conversation_summary_draft(
        ConversationSummaryGenerationRequest(
            session_id="session-1",
            channel="youzan",
            user_id="buyer-1",
            existing_summary_text="客户早前问过配送。",
            messages=[
                _message("msg-1", MessageRole.USER, "想订生日蛋糕"),
                _message("msg-2", MessageRole.TOOL, "工具结果不应进入摘要"),
                _message("msg-3", MessageRole.ASSISTANT, "需要确认配送时间"),
            ],
        )
    )

    assert draft is not None
    assert draft.session_id == "session-1"
    assert draft.summary_text.startswith("客户目标：想确认生日蛋糕配送")
    assert "工具结果" not in captured_messages[1]["content"]
    assert draft.source_message_ids_json == '["msg-1", "msg-3"]'
    assert draft.source_until_message_id == "msg-3"
    state = json.loads(draft.state_json)
    assert state["pending_questions"] == ["配送时间待确认"]
    assert state["source_scope"] == {
        "from_message_id": "msg-1",
        "until_message_id": "msg-3",
    }
    assert draft.token_estimate > 0


@pytest.mark.asyncio
async def test_generate_conversation_summary_draft_returns_none_for_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_summary_chain(*args: object, **kwargs: object) -> str:
        return "not json"

    monkeypatch.setattr(summary_module, "_invoke_summary_chain", fake_summary_chain)

    draft = await generate_conversation_summary_draft(
        ConversationSummaryGenerationRequest(
            session_id="session-2",
            channel="youzan",
            user_id="buyer-2",
            messages=[_message("msg-1", MessageRole.USER, "继续聊")],
        )
    )

    assert draft is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sensitive_text",
    [
        "客户手机号是 13812345678",
        "配送地址是北京市朝阳区隐私路99号2单元301室",
        "订单号是 E202605240001",
    ],
)
async def test_generate_conversation_summary_draft_discards_sensitive_output(
    monkeypatch: pytest.MonkeyPatch,
    sensitive_text: str,
) -> None:
    async def fake_summary_chain(*args: object, **kwargs: object) -> str:
        return json.dumps(
            {
                "customer_goal": sensitive_text,
                "confirmed_facts": [],
                "pending_questions": [],
                "service_boundaries": [],
                "handoff_state": "none",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(summary_module, "_invoke_summary_chain", fake_summary_chain)

    draft = await generate_conversation_summary_draft(
        ConversationSummaryGenerationRequest(
            session_id="session-3",
            channel="youzan",
            user_id="buyer-3",
            messages=[_message("msg-1", MessageRole.USER, "敏感信息测试")],
        )
    )

    assert draft is None


@pytest.mark.asyncio
async def test_generate_conversation_summary_draft_discards_overlong_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_summary_chain(*args: object, **kwargs: object) -> str:
        return json.dumps(
            {
                "customer_goal": "长" * 900,
                "confirmed_facts": [],
                "pending_questions": [],
                "service_boundaries": [],
                "handoff_state": "none",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(summary_module, "_invoke_summary_chain", fake_summary_chain)

    draft = await generate_conversation_summary_draft(
        ConversationSummaryGenerationRequest(
            session_id="session-4",
            channel="youzan",
            user_id="buyer-4",
            messages=[_message("msg-1", MessageRole.USER, "长摘要测试")],
        )
    )

    assert draft is None


@pytest.mark.asyncio
async def test_generate_conversation_summary_draft_returns_none_on_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_summary_chain(*args: object, **kwargs: object) -> str:
        raise LLMError("llm failed")

    monkeypatch.setattr(summary_module, "_invoke_summary_chain", fake_summary_chain)

    draft = await generate_conversation_summary_draft(
        ConversationSummaryGenerationRequest(
            session_id="session-5",
            channel="youzan",
            user_id="buyer-5",
            messages=[_message("msg-1", MessageRole.USER, "LLM 异常测试")],
        )
    )

    assert draft is None


@pytest.mark.asyncio
async def test_generate_conversation_summary_draft_skips_tool_only_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_summary_chain(*args: object, **kwargs: object) -> str:
        raise AssertionError("不应为纯工具消息调用 LLM")

    monkeypatch.setattr(summary_module, "_invoke_summary_chain", fake_summary_chain)

    draft = await generate_conversation_summary_draft(
        ConversationSummaryGenerationRequest(
            session_id="session-6",
            channel="youzan",
            user_id="buyer-6",
            messages=[_message("msg-1", MessageRole.TOOL, "工具结果")],
        )
    )

    assert draft is None


@pytest.mark.asyncio
async def test_summary_chain_redacts_inputs_before_prompt_runnable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def capture_prompt(prompt_value, **_kwargs) -> str:
        captured.append(prompt_value.to_string())
        return "{}"

    monkeypatch.setattr(
        summary_module,
        "get_langchain_chat_model",
        lambda **_kwargs: RunnableLambda(capture_prompt),
    )

    result = await summary_module._invoke_summary_chain(
        [_message("msg-1", MessageRole.USER, "手机号 13812345678")],
        "订单 E1234567890123",
    )

    assert result == "{}"
    assert "13812345678" not in captured[0]
    assert "E1234567890123" not in captured[0]


def _message(message_id: str, role: MessageRole, content: str) -> Message:
    return Message(
        id=message_id,
        session_id="session-test",
        role=role,
        content=content,
    )
