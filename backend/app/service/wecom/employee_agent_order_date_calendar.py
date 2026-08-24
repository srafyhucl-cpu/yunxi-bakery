"""企微员工助手订单日历表达解析。"""

from __future__ import annotations

import re
from datetime import date, timedelta

WEEKEND_START_OFFSET = 5
WEEKEND_END_OFFSET = 6
MONTH_DAY_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*(?:日|号)?")
SLASH_DATE_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s*[/-]\s*(\d{1,2})(?!\d)")
WEEKDAY_PATTERN = re.compile(r"(下)?(?:周|星期)([一二三四五六日天])")
WEEKDAY_ALIASES = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}


def remove_calendar_expressions(query: str) -> str:
    """移除会污染商品关键词的日历表达。"""
    keyword = MONTH_DAY_PATTERN.sub(" ", query)
    keyword = WEEKDAY_PATTERN.sub(" ", keyword)
    return SLASH_DATE_PATTERN.sub(" ", keyword)


def resolve_weekend_range(today: date) -> tuple[str, str]:
    week_start = today - timedelta(days=today.weekday())
    weekend_start = week_start + timedelta(days=WEEKEND_START_OFFSET)
    weekend_end = week_start + timedelta(days=WEEKEND_END_OFFSET)
    if today > weekend_end:
        weekend_start += timedelta(days=7)
        weekend_end += timedelta(days=7)
    return weekend_start.isoformat(), weekend_end.isoformat()


def extract_specific_month_day(query: str, today: date) -> date | None:
    match = MONTH_DAY_PATTERN.search(query) or SLASH_DATE_PATTERN.search(query)
    if match is None:
        return None
    month = int(match.group(1))
    day = int(match.group(2))
    try:
        return date(today.year, month, day)
    except ValueError:
        return None


def extract_weekday(query: str, today: date) -> date | None:
    match = WEEKDAY_PATTERN.search(query)
    if match is None:
        return None
    target_weekday = WEEKDAY_ALIASES[match.group(2)]
    week_start = today - timedelta(days=today.weekday())
    offset_days = target_weekday + (7 if match.group(1) else 0)
    return week_start + timedelta(days=offset_days)
