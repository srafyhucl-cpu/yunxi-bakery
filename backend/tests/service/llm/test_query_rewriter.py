from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables import RunnableLambda

from app.service.llm.query_rewriter import _invoke_rewrite_chain, rewrite_query


@pytest.mark.asyncio
async def test_rewrite_query_uses_runnable_output_and_strips_quotes() -> None:
    with patch(
        "app.service.llm.query_rewriter._invoke_rewrite_chain",
        new=AsyncMock(return_value='"草莓蛋糕支持同城配送吗？"'),
    ) as invoke_chain:
        rewritten = await rewrite_query("那配送吗？", "用户：草莓蛋糕怎么卖？")

    assert rewritten == "草莓蛋糕支持同城配送吗？"
    invoke_chain.assert_awaited_once_with(
        history="用户：草莓蛋糕怎么卖？",
        user_query="那配送吗？",
    )


@pytest.mark.asyncio
async def test_rewrite_query_returns_original_input_when_chain_fails() -> None:
    with patch(
        "app.service.llm.query_rewriter._invoke_rewrite_chain",
        new=AsyncMock(side_effect=RuntimeError("provider unavailable")),
    ):
        rewritten = await rewrite_query("那配送吗？", "用户：草莓蛋糕怎么卖？")

    assert rewritten == "那配送吗？"


@pytest.mark.asyncio
async def test_rewrite_query_skips_single_character_input() -> None:
    with patch(
        "app.service.llm.query_rewriter._invoke_rewrite_chain",
        new=AsyncMock(),
    ) as invoke_chain:
        rewritten = await rewrite_query("？")

    assert rewritten == "？"
    invoke_chain.assert_not_awaited()


@pytest.mark.asyncio
async def test_rewrite_chain_redacts_inputs_before_prompt_runnable() -> None:
    captured: list[str] = []

    def capture_prompt(prompt_value, **_kwargs) -> str:
        captured.append(prompt_value.to_string())
        return "改写后的问题"

    with patch(
        "app.service.llm.query_rewriter.get_langchain_chat_model",
        return_value=RunnableLambda(capture_prompt),
    ):
        rewritten = await _invoke_rewrite_chain(
            history="用户：我的手机号是 13812345678",
            user_query="这个订单 E1234567890123 怎么办？",
        )

    assert rewritten == "改写后的问题"
    assert captured
    assert "13812345678" not in captured[0]
    assert "E1234567890123" not in captured[0]
