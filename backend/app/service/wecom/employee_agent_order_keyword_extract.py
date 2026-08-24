"""企微员工助手订单关键词提取。"""

from __future__ import annotations

import re

from app.service.wecom.employee_agent_order_constants import (
    ORDER_NO_PATTERN,
    ORDER_QUERY_PUNCTUATION_PATTERN,
    ORDER_STATUS_KEYWORDS,
)
from app.service.wecom.employee_agent_order_date import remove_order_time_expressions
from app.service.wecom.employee_agent_order_delivery_time import (
    remove_delivery_time_expressions,
)
from app.service.wecom.employee_agent_order_predicates import (
    has_customer_history_intent,
)
from app.service.wecom.employee_agent_order_stop_words import ORDER_QUERY_STOP_WORDS

ORDER_STATUS_STOP_WORDS = tuple(
    dict.fromkeys(
        keyword
        for status_keywords in ORDER_STATUS_KEYWORDS.values()
        for keyword in status_keywords
    )
)


def extract_order_keyword(query: str) -> str:
    """从员工订单问法中提取商品/订单检索关键词。"""
    if has_customer_history_intent(query):
        return ""
    keyword = remove_order_time_expressions(query.strip())
    keyword = remove_delivery_time_expressions(keyword)
    stop_words = ORDER_QUERY_STOP_WORDS + ORDER_STATUS_STOP_WORDS
    for stop_word in sorted(stop_words, key=len, reverse=True):
        keyword = keyword.replace(stop_word, " ")
    keyword = re.sub(r"E\d{12,}", " ", keyword, flags=re.IGNORECASE)
    keyword = ORDER_NO_PATTERN.sub(" ", keyword)
    keyword = ORDER_QUERY_PUNCTUATION_PATTERN.sub(" ", keyword)
    return " ".join(keyword.split())
