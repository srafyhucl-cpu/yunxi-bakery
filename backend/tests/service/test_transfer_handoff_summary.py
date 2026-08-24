import pytest
from langchain_core.runnables import RunnableLambda

from app.service.chat_transfer import (
    build_transfer_summary,
    build_transfer_summary_fallback,
)
from app.service.transfer_handoff_summary import (
    HandoffSummaryInput,
    _invoke_handoff_summary_chain,
    build_handoff_note_with_llm,
)


def test_build_transfer_summary_fallback_returns_decision_note_for_elder_case() -> None:
    history = "\n".join(
        [
            "用户：给老人买个木糖醇的蛋糕",
            "AI：推荐星星人奶油蛋糕",
            "用户：10个人吃推荐一个",
            "AI：星星人支持10寸",
            "用户：星星人也不适合老人啊",
        ]
    )

    note = build_transfer_summary_fallback("转人工", history)

    assert "客户诉求：给老人/长辈选蛋糕" in note
    assert "偏木糖醇/低糖" in note
    assert "当前卡点：客户已表达推荐不认可" in note
    assert "优先推荐祝寿/稳重/寓意明确款" in note
    assert "AI：推荐星星人" not in note


@pytest.mark.asyncio
async def test_build_transfer_summary_uses_llm_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_llm(
        messages: list[dict], temperature: float, max_tokens: int
    ) -> str:
        captured["messages"] = messages
        captured["temperature"] = temperature
        captured["max_tokens"] = max_tokens
        return "客户诉求：想订低糖生日蛋糕；当前卡点：图片款式待确认；建议接手：先确认图片款和配送时间"

    note = await build_handoff_note_with_llm(
        HandoffSummaryInput(
            reason="用户要求转人工",
            history_text="用户：我发的图片这个款式能做吗\nAI：我先帮您看看",
        ),
        llm_caller=fake_llm,
    )

    assert "图片款式待确认" in note
    assert "配送时间" in note
    assert captured["temperature"] == 0.1
    assert captured["max_tokens"] == 220
    assert "最近接待记录" in captured["messages"][1]["content"]


@pytest.mark.asyncio
async def test_build_transfer_summary_falls_back_when_llm_fails() -> None:
    async def broken_llm(
        messages: list[dict], temperature: float, max_tokens: int
    ) -> str:
        raise RuntimeError("model unavailable")

    note = await build_handoff_note_with_llm(
        HandoffSummaryInput(
            reason="转人工",
            history_text="用户：给老人买个少糖蛋糕\n用户：8个人吃",
        ),
        llm_caller=broken_llm,
    )

    assert "客户诉求：给老人/长辈选蛋糕" in note
    assert "偏木糖醇/低糖" in note


@pytest.mark.asyncio
async def test_build_transfer_summary_public_entrypoint_is_async(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_build(payload: HandoffSummaryInput) -> str:
        return f"客户诉求：{payload.reason}"

    monkeypatch.setattr(
        "app.service.chat_transfer.build_handoff_note_with_llm", fake_build
    )

    note = await build_transfer_summary("需要人工", "用户：帮我看看图片")

    assert note == "客户诉求：需要人工"


@pytest.mark.asyncio
async def test_handoff_chain_redacts_inputs_before_prompt_runnable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def capture_prompt(prompt_value, **_kwargs) -> str:
        captured.append(prompt_value.to_string())
        return "客户诉求：待确认；当前卡点：待确认；建议接手：人工确认"

    monkeypatch.setattr(
        "app.service.transfer_handoff_summary.get_langchain_chat_model",
        lambda **_kwargs: RunnableLambda(capture_prompt),
    )

    note = await _invoke_handoff_summary_chain(
        HandoffSummaryInput(
            reason="用户手机号 13812345678 要求转人工",
            history_text="用户：订单 E1234567890123 还没收到",
        )
    )

    assert "13812345678" not in captured[0]
    assert "E1234567890123" not in captured[0]
    assert "人工确认" in note
