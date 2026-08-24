"""意图识别测试。"""

import pytest

from app.exceptions import LLMError
from app.service.llm import intent as intent_module


@pytest.mark.parametrize(
    ("query", "expected_intent"),
    [
        ("提拉米苏多少钱", intent_module.IntentType.PRODUCT_CONSULTATION),
        ("可以开发票吗", intent_module.IntentType.STORE_POLICY),
        ("运费多少钱", intent_module.IntentType.SHIPPING_FEE),
        ("明天下午能送到吗", intent_module.IntentType.DELIVERY_SCHEDULE),
        ("给我开发票", intent_module.IntentType.ORDER_SERVICE),
        ("帮我改一下配送地址", intent_module.IntentType.ORDER_SERVICE),
        ("蛋糕塌了我要退款", intent_module.IntentType.AFTER_SALES_ISSUE),
        ("转人工", intent_module.IntentType.HUMAN_ASSISTANCE),
        ("你好呀", intent_module.IntentType.SMALL_TALK),
    ],
)
def test_match_clear_intent(
    query: str, expected_intent: intent_module.IntentType
) -> None:
    assert intent_module._match_clear_intent(query) == expected_intent


@pytest.mark.asyncio
async def test_detect_intent_uses_llm_for_ambiguous_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_chain(*args: object, **kwargs: object) -> str:
        return '{"primary_intent": 2, "secondary_intents": []}'

    monkeypatch.setattr(intent_module, "_invoke_intent_chain", _fake_chain)

    intent = await intent_module.detect_intent("开发票")

    assert intent == intent_module.IntentType.STORE_POLICY


@pytest.mark.asyncio
async def test_detect_intent_falls_back_when_llm_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_llm_error(*args: object, **kwargs: object) -> str:
        raise LLMError("boom")

    monkeypatch.setattr(intent_module, "_invoke_intent_chain", _raise_llm_error)

    intent = await intent_module.detect_intent("这个呢")

    assert intent == intent_module.IntentType.PRODUCT_CONSULTATION


@pytest.mark.parametrize(
    "noise_query",
    [
        "   ",
        "!!!???",
        "🎂🍰🎂",
        "……——",
    ],
)
@pytest.mark.asyncio
async def test_detect_intent_filters_noise_to_small_talk(noise_query: str) -> None:
    # 极端噪声不应该调用大模型，直接返回 SMALL_TALK
    intent = await intent_module.detect_intent(noise_query)
    assert intent == intent_module.IntentType.SMALL_TALK


@pytest.mark.asyncio
async def test_detect_intent_bypasses_llm_for_human_assistance_keywords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_error(*args: object, **kwargs: object) -> None:
        raise AssertionError("不应该调用任何后续大模型接口")

    monkeypatch.setattr(intent_module, "_invoke_intent_chain", _raise_error)

    intent = await intent_module.detect_intent("我要人工客服")
    assert intent == intent_module.IntentType.HUMAN_ASSISTANCE


@pytest.mark.parametrize(
    ("raw_response", "expected_intent"),
    [
        (
            '{"primary_intent": 2, "secondary_intents": [7]}',
            intent_module.IntentType.HUMAN_ASSISTANCE,
        ),
        (
            '{"primary_intent": 1, "secondary_intents": [6]}',
            intent_module.IntentType.AFTER_SALES_ISSUE,
        ),
        (
            '{"primary_intent": 2, "secondary_intents": [5]}',
            intent_module.IntentType.ORDER_SERVICE,
        ),
        (
            '```json\n{"primary_intent": 6, "secondary_intents": []}\n```',
            intent_module.IntentType.AFTER_SALES_ISSUE,
        ),
        ("7", intent_module.IntentType.HUMAN_ASSISTANCE),
        ("broken json containing 6", intent_module.IntentType.AFTER_SALES_ISSUE),
        ("completely broken", intent_module.IntentType.PRODUCT_CONSULTATION),
    ],
)
def test_extract_intent_prioritization_and_parsing(
    raw_response: str, expected_intent: intent_module.IntentType
) -> None:
    assert intent_module._extract_intent(raw_response) == expected_intent
