"""企微员工助手订单时间范围解析。"""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.service.wecom.employee_agent_order_constants import (
    CHINESE_DAY_NUMBERS,
    MAX_RESULT_LIMIT,
)
from app.service.wecom.employee_agent_order_keywords import (
    ORDER_PREORDER_DELIVERY_KEYWORDS,
)
from app.service.wecom.employee_agent_order_date_calendar import (
    extract_specific_month_day,
    extract_weekday,
    remove_calendar_expressions,
    resolve_weekend_range,
)

ORDER_DATE_FIELD = "order_time"
DELIVERY_DATE_FIELD = "delivery_time"


def resolve_order_date_range(query: str, today: date) -> tuple[str, str]:
    """把员工口语时间范围转成订单查询日期边界。"""
    recent_days = extract_recent_days(query)
    if recent_days is not None:
        date_from = today - timedelta(days=recent_days - 1)
        return date_from.isoformat(), today.isoformat()
    if any(word in query for word in ("上周", "上星期")):
        week_start = today - timedelta(days=today.weekday())
        previous_week_start = week_start - timedelta(days=7)
        previous_week_end = week_start - timedelta(days=1)
        return previous_week_start.isoformat(), previous_week_end.isoformat()
    if any(word in query for word in ("本周", "这周", "本星期", "这个星期")):
        week_start = today - timedelta(days=today.weekday())
        return week_start.isoformat(), today.isoformat()
    if any(word in query for word in ("本月", "这个月", "当月")):
        month_start = today.replace(day=1)
        return month_start.isoformat(), today.isoformat()
    if any(word in query for word in ("本周末", "这个周末", "周末")):
        return resolve_weekend_range(today)
    if "后天" in query:
        target_day = today + timedelta(days=2)
        return target_day.isoformat(), target_day.isoformat()
    if "明天" in query:
        target_day = today + timedelta(days=1)
        return target_day.isoformat(), target_day.isoformat()
    if "昨天" in query:
        target_day = today - timedelta(days=1)
        return target_day.isoformat(), target_day.isoformat()
    if any(
        word in query
        for word in ("今天", "今日", "上午", "中午", "下午", "傍晚", "晚上", "夜里")
    ):
        return today.isoformat(), today.isoformat()
    weekday_day = extract_weekday(query, today)
    if weekday_day is not None:
        return weekday_day.isoformat(), weekday_day.isoformat()
    specific_day = extract_specific_month_day(query, today)
    if specific_day is not None:
        return specific_day.isoformat(), specific_day.isoformat()
    return "", ""


def remove_order_time_expressions(query: str) -> str:
    """移除会污染商品关键词的相对时间表达。"""
    keyword = re.sub(r"(?:最近|近)\s*\d+\s*天", " ", query)
    keyword = re.sub(r"(?:最近|近)\s*[一二三四五六七八九十]\s*天", " ", keyword)
    return remove_calendar_expressions(keyword)


def extract_recent_days(query: str) -> int | None:
    match = re.search(r"(?:最近|近)\s*(\d+)\s*天", query)
    if match:
        return max(1, min(int(match.group(1)), MAX_RESULT_LIMIT))
    chinese_match = re.search(r"(?:最近|近)\s*([一二三四五六七八九十])\s*天", query)
    if chinese_match:
        days = CHINESE_DAY_NUMBERS.get(chinese_match.group(1), 0)
        return max(1, min(days, MAX_RESULT_LIMIT)) if days else None
    if any(word in query for word in ("近一周", "最近一周", "最近7天", "近7天")):
        return 7
    return None


def resolve_order_date_field(query: str) -> str:
    """解析订单日期过滤口径。"""
    if any(
        word in query
        for word in (
            "约送",
            "配送",
            "送达",
            "送到",
            *ORDER_PREORDER_DELIVERY_KEYWORDS,
            "履约",
            "发货压力",
            "快超时",
            "要超时",
            "来不及",
            "待处理",
            "上午",
            "中午",
            "下午",
            "傍晚",
            "晚上",
            "夜里",
        )
    ):
        return DELIVERY_DATE_FIELD
    return ORDER_DATE_FIELD
