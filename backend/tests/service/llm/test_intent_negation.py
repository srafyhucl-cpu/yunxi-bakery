"""否定语境下意图拦截的边缘用例测试。

验证当用户输入中包含否定引导词（如"不用"、"不需要"）时，
关键词拦截器不会误触发转人工或售后异常意图（L-7.1）。
"""

from app.service.llm.intent import _match_clear_intent, _has_negation
from app.service.llm.intent_types import IntentType


class TestNegationDetection:
    """否定引导词检测函数测试。"""

    def test_negation_detected(self) -> None:
        assert _has_negation("不用转人工") is True

    def test_negation_detected_prefix_variant(self) -> None:
        assert _has_negation("不需要退款") is True

    def test_no_negation_in_normal_query(self) -> None:
        assert _has_negation("转人工") is False

    def test_no_negation_in_product_query(self) -> None:
        assert _has_negation("草莓蛋糕多少钱") is False


class TestNegationBypassHumanAssistance:
    """否定语境下转人工拦截应被跳过。"""

    def test_no_transfer_when_negated(self) -> None:
        """'不用转人工，我自己看看' 不应命中 HUMAN_ASSISTANCE。"""
        result = _match_clear_intent("不用转人工我自己看看")
        assert result != IntentType.HUMAN_ASSISTANCE

    def test_no_transfer_when_unnecessary(self) -> None:
        """'不需要人工客服' 不应命中 HUMAN_ASSISTANCE。"""
        result = _match_clear_intent("不需要人工客服")
        assert result != IntentType.HUMAN_ASSISTANCE

    def test_transfer_still_works_positive(self) -> None:
        """正向用例：'转人工' 仍应命中 HUMAN_ASSISTANCE。"""
        result = _match_clear_intent("转人工")
        assert result == IntentType.HUMAN_ASSISTANCE

    def test_transfer_still_works_find_agent(self) -> None:
        """正向用例：'找客服' 仍应命中 HUMAN_ASSISTANCE。"""
        result = _match_clear_intent("找客服")
        assert result == IntentType.HUMAN_ASSISTANCE


class TestNegationBypassAfterSales:
    """否定语境下售后拦截应被跳过。"""

    def test_no_aftersales_when_negated(self) -> None:
        """'不需要退款' 不应命中 AFTER_SALES_ISSUE。"""
        result = _match_clear_intent("不需要退款")
        assert result != IntentType.AFTER_SALES_ISSUE

    def test_refund_question_not_intercepted(self) -> None:
        """'可以退款吗' 是问句场景，不应被拦截为售后异常。"""
        result = _match_clear_intent("可以退款吗")
        assert result != IntentType.AFTER_SALES_ISSUE

    def test_aftersales_still_works_positive(self) -> None:
        """正向用例：'退款' 仍应命中 AFTER_SALES_ISSUE。"""
        result = _match_clear_intent("退款")
        assert result == IntentType.AFTER_SALES_ISSUE

    def test_aftersales_still_works_complaint(self) -> None:
        """正向用例：'投诉' 仍应命中 AFTER_SALES_ISSUE。"""
        result = _match_clear_intent("投诉")
        assert result == IntentType.AFTER_SALES_ISSUE
