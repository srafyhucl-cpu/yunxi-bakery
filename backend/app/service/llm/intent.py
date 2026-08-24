"""意图识别服务。"""

import json
from functools import lru_cache

from app.exceptions import LLMError
from app.logger import setup_logger
from app.service.agents.llm import get_langchain_chat_model
from app.service.privacy_redaction import redact_external_text
from app.service.llm.intent_types import INTENT_ID_CHARACTERS
from app.service.llm.intent_prompt import INTENT_PROMPT
from app.service.llm.intent_domain_keywords import (
    DELIVERY_SCHEDULE_KEYWORDS,
    ORDER_SERVICE_TOPIC_KEYWORDS,
    PRODUCT_KEYWORDS,
    SHIPPING_FEE_KEYWORDS,
    SMALL_TALK_KEYWORDS,
    STORE_POLICY_KEYWORDS,
)
from app.service.llm.intent_behavior_keywords import (
    AFTER_SALES_KEYWORDS,
    HUMAN_ASSISTANCE_KEYWORDS,
    NEGATION_PREFIXES,
    ORDER_ACTION_KEYWORDS,
    ORDER_CONTEXT_KEYWORDS,
    QUESTION_KEYWORDS,
)
from app.service.llm.intent_types import IntentType


logger = setup_logger()

# 闲聊拦截的最大查询字符数（超出此长度则放行到后续意图流程）
SMALL_TALK_MAX_QUERY_LEN = 12
# 意图识别 LLM 调用的 max_tokens（输出仅为小数字或简短 JSON，严格限制）
INTENT_LLM_MAX_TOKENS = 32


@lru_cache(maxsize=1)
def _get_intent_prompt_template():
    """延迟构建意图识别提示模板，避免模块导入阶段加载重依赖。"""
    from langchain_core.prompts import ChatPromptTemplate

    return ChatPromptTemplate.from_template(INTENT_PROMPT)


def _contains_any(user_query: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in user_query for keyword in keywords)


def _looks_like_question(user_query: str) -> bool:
    return _contains_any(user_query, QUESTION_KEYWORDS)


def _has_negation(user_query: str) -> bool:
    """检测用户输入是否包含否定性引导词。"""
    return _contains_any(user_query, NEGATION_PREFIXES)


def _match_clear_intent(user_query: str) -> IntentType | None:
    has_question_signal = _looks_like_question(user_query)
    has_negation = _has_negation(user_query)
    # 否定语境下不做强动作拦截，放行到 LLM 判断
    if _contains_any(user_query, HUMAN_ASSISTANCE_KEYWORDS) and not has_negation:
        return IntentType.HUMAN_ASSISTANCE
    if _contains_any(user_query, AFTER_SALES_KEYWORDS) and not has_negation:
        # 问句场景放行到 RAG 作答而非直接拦截
        if not has_question_signal:
            return IntentType.AFTER_SALES_ISSUE
    has_order_action = _contains_any(user_query, ORDER_ACTION_KEYWORDS)
    has_order_context = _contains_any(user_query, ORDER_CONTEXT_KEYWORDS)
    has_order_topic = _contains_any(user_query, ORDER_SERVICE_TOPIC_KEYWORDS)
    if has_order_topic and (
        has_order_action or (has_order_context and not has_question_signal)
    ):
        return IntentType.ORDER_SERVICE
    if (
        _contains_any(user_query, SMALL_TALK_KEYWORDS)
        and len(user_query) <= SMALL_TALK_MAX_QUERY_LEN
        and not has_question_signal
    ):
        return IntentType.SMALL_TALK
    if not has_question_signal:
        return None
    if _contains_any(user_query, SHIPPING_FEE_KEYWORDS):
        return IntentType.SHIPPING_FEE
    if _contains_any(user_query, DELIVERY_SCHEDULE_KEYWORDS):
        return IntentType.DELIVERY_SCHEDULE
    if _contains_any(user_query, STORE_POLICY_KEYWORDS):
        return IntentType.STORE_POLICY
    if _contains_any(user_query, PRODUCT_KEYWORDS):
        return IntentType.PRODUCT_CONSULTATION
    return None


def _extract_intent(raw_content: str) -> IntentType:
    try:
        # 清理可能包含的 Markdown json 包裹标记
        cleaned_content = raw_content.strip()
        if cleaned_content.startswith("```json"):
            cleaned_content = cleaned_content.removeprefix("```json")
        if cleaned_content.endswith("```"):
            cleaned_content = cleaned_content.removesuffix("```")
        cleaned_content = cleaned_content.strip()

        intent_response = json.loads(cleaned_content)
        if isinstance(intent_response, int):
            primary = intent_response
            secondaries = []
        elif isinstance(intent_response, dict):
            primary = int(intent_response.get("primary_intent", 1))
            secondaries = [int(i) for i in intent_response.get("secondary_intents", [])]
        else:
            raise TypeError("Expected dict or int")

        all_intents = [primary] + secondaries

        # 优先级晋升：人工服务 (7) > 售后异常 (6) > 订单办理 (5)
        if IntentType.HUMAN_ASSISTANCE in all_intents:
            return IntentType.HUMAN_ASSISTANCE
        if IntentType.AFTER_SALES_ISSUE in all_intents:
            return IntentType.AFTER_SALES_ISSUE
        if IntentType.ORDER_SERVICE in all_intents:
            return IntentType.ORDER_SERVICE

        # 兜底返回主意图
        _safe_intents = (
            IntentType.PRODUCT_CONSULTATION,
            IntentType.STORE_POLICY,
            IntentType.SHIPPING_FEE,
            IntentType.DELIVERY_SCHEDULE,
            IntentType.SMALL_TALK,
        )
        if primary in _safe_intents:
            return IntentType(primary)
        return IntentType.PRODUCT_CONSULTATION
    except (json.JSONDecodeError, ValueError, TypeError, KeyError):
        # 兜底：如果 JSON 无法解析，回退到数字提取
        for character in raw_content:
            if character in INTENT_ID_CHARACTERS:
                val = int(character)
                # 优先级判定
                if val in (
                    IntentType.ORDER_SERVICE,
                    IntentType.AFTER_SALES_ISSUE,
                    IntentType.HUMAN_ASSISTANCE,
                ):
                    if val == IntentType.HUMAN_ASSISTANCE:
                        return IntentType.HUMAN_ASSISTANCE
                    if val == IntentType.AFTER_SALES_ISSUE:
                        return IntentType.AFTER_SALES_ISSUE
                    return IntentType.ORDER_SERVICE
                return IntentType(val)
        return IntentType.PRODUCT_CONSULTATION


async def detect_intent(user_query: str, history: str = "") -> IntentType:
    normalized_query = "".join(user_query.split())
    # 1. 过滤极端噪声（空白、纯标点、纯 emoji 符号）
    if not normalized_query or not any(char.isalnum() for char in normalized_query):
        return IntentType.SMALL_TALK

    # 2. 0 成本强动作拦截（否定语境跳过，放行到 LLM 进一步判断）
    if _contains_any(normalized_query, HUMAN_ASSISTANCE_KEYWORDS) and not _has_negation(
        normalized_query
    ):
        logger.debug(
            '转人工强动作拦截命中: "%s" -> HUMAN_ASSISTANCE', normalized_query[:30]
        )
        return IntentType.HUMAN_ASSISTANCE

    # 3. 其它明确规则的前置判定
    matched_intent = _match_clear_intent(normalized_query)
    if matched_intent is not None:
        logger.debug(
            '意图识别前置命中: "%s" -> %s', normalized_query[:30], matched_intent.name
        )
        return matched_intent

    # 4. 大模型多标签打标与 Token 溢出防线
    try:
        raw_content = await _invoke_intent_chain(
            history=history or "无",
            user_query=normalized_query,
        )
        raw_content = (raw_content or "1").strip()
        intent = _extract_intent(raw_content)
        logger.debug('意图识别: "%s" -> %s', normalized_query[:30], intent.name)
        return intent
    except (LLMError, KeyError, IndexError) as exc:
        logger.warning("意图识别失败，默认返回 PRODUCT_CONSULTATION: %s", exc)
        return IntentType.PRODUCT_CONSULTATION


async def _invoke_intent_chain(*, history: str, user_query: str) -> str:
    """通过统一 LangChain Runnable 执行意图识别。"""
    try:
        from langchain_core.output_parsers import StrOutputParser

        model = get_langchain_chat_model(provider="mimo", temperature=0).bind(
            max_tokens=INTENT_LLM_MAX_TOKENS
        )
        chain = _get_intent_prompt_template() | model | StrOutputParser()
        return await chain.ainvoke(
            {
                "history": redact_external_text(history),
                "user_query": redact_external_text(user_query),
            }
        )
    except Exception as exc:
        raise LLMError("意图识别 LLM 调用失败") from exc
