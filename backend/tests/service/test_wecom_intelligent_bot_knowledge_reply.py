from app.service.wecom.intelligent_bot_tools import WeComBotBusinessToolService
from app.service.wecom.intelligent_bot_knowledge_format import knowledge_answer_text


class _EmptyKnowledgeRetriever:
    async def search_keyword_only(self, question: str, limit: int = 5) -> list[object]:
        return []


async def test_delivery_knowledge_fallback_stays_on_delivery_rule() -> None:
    service = WeComBotBusinessToolService(
        knowledge_retriever=_EmptyKnowledgeRetriever()
    )

    payload = await service.answer_knowledge({"question": "明天能配送吗"})

    assert payload["ok"] is True
    assert "配送" in payload["result"]
    assert "门店实际排期" in payload["result"]
    assert "转人工确认" in payload["result"]
    assert "不要承诺一定准时送达" in payload["result"]
    assert "知识库没有命中" not in payload["result"]
    assert "订单尾号" not in payload["result"]
    assert "订单状态" not in payload["result"]


async def test_refund_knowledge_fallback_stays_on_refund_guardrail() -> None:
    service = WeComBotBusinessToolService(
        knowledge_retriever=_EmptyKnowledgeRetriever()
    )

    payload = await service.answer_knowledge({"question": "退款规则是什么"})

    assert payload["ok"] is True
    assert "退款/售后规则" in payload["result"]
    assert "订单状态" in payload["result"]
    assert "不要直接承诺可退金额或到账时间" in payload["result"]
    assert "转人工确认" in payload["result"]
    assert "未找到匹配知识" not in payload["result"]


def test_general_empty_knowledge_keeps_plain_miss() -> None:
    assert knowledge_answer_text("会员规则是什么", []) == "未找到匹配知识。"
