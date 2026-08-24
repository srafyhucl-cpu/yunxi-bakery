"""确定性回复校验门。"""

import json
import re
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.logger import setup_logger
from app.models.session import Session
from app.utils import now_str

logger = setup_logger()

REPLY_GUARD_EVENT_TYPE = "reply_guard_hit"
REPLY_GUARD_EVENT_SOURCE = "chat_pipeline"
PRICE_CONFIRMATION_TEXT = "具体价格请咨询客服确认~"
DELIVERY_CONFIRMATION_TEXT = "具体配送时间以门店实际排期为准~"
FOOD_SAFETY_NOTICE = (
    "涉及过敏、成分或食品安全问题，建议联系人工客服确认，AI 不替您判断能否食用~"
)

PRICE_PATTERN = re.compile(r"(?:￥|¥)?\s*\d+(?:\.\d+)?\s*(?:元|块)")
PRODUCT_TITLE_PATTERN = re.compile(r"《([^》]+)》")
DELIVERY_PROMISE_PATTERN = re.compile(
    r"(今天|明天|后天|周[一二三四五六日天]|星期[一二三四五六日天]|\d{1,2}[点:：]\d{0,2})"
    r"[^。！？!?，,\n]{0,16}(送达|送到|配送|发货|到达)"
)
FOOD_SAFETY_KEYWORDS = (
    "过敏",
    "成分",
    "孕妇",
    "糖尿病",
    "乳糖不耐",
    "能不能吃",
    "可以吃吗",
    "食品安全",
    "医疗",
    "医生",
)


@dataclass(frozen=True)
class ReplyGuardContext:
    analytics_repo: Any
    session: Session
    user_id: str
    channel: str
    product_titles: tuple[str, ...] = ()
    source_text: str = ""


async def apply_reply_guard(
    reply: str | None, context: ReplyGuardContext
) -> str | None:
    """按开关执行确定性校验，命中时记录埋点。"""
    if not settings.ENABLE_REPLY_GUARD or not reply:
        return reply

    guarded_reply = reply
    hit_rules: list[str] = []

    guarded_reply, product_hits = _guard_product_titles(
        guarded_reply, context.product_titles
    )
    hit_rules.extend(product_hits)

    guarded_reply, price_hits = _guard_prices(guarded_reply, context.source_text)
    hit_rules.extend(price_hits)

    guarded_reply, delivery_hits = _guard_delivery_promises(guarded_reply)
    hit_rules.extend(delivery_hits)

    guarded_reply, safety_hits = _guard_food_safety(guarded_reply)
    hit_rules.extend(safety_hits)

    if hit_rules:
        await _record_guard_hit(context, hit_rules)
    return guarded_reply


def _guard_product_titles(
    reply: str, product_titles: tuple[str, ...]
) -> tuple[str, list[str]]:
    if not product_titles:
        return reply, []

    allowed_titles = set(product_titles)
    hit_rules: list[str] = []

    def replace_title(match: re.Match[str]) -> str:
        title = match.group(1)
        if title in allowed_titles:
            return match.group(0)
        hit_rules.append("product_whitelist")
        return "该商品"

    return PRODUCT_TITLE_PATTERN.sub(replace_title, reply), hit_rules


def _guard_prices(reply: str, source_text: str) -> tuple[str, list[str]]:
    compact_source = _compact_text(source_text)
    unsupported_prices = [
        match.group(0)
        for match in PRICE_PATTERN.finditer(reply)
        if not _is_price_supported(match.group(0), compact_source)
    ]
    if not unsupported_prices:
        return reply, []

    guarded_reply = reply
    for price in unsupported_prices:
        guarded_reply = guarded_reply.replace(price, "具体价格")
    guarded_reply = _append_once(guarded_reply, PRICE_CONFIRMATION_TEXT)
    return guarded_reply, ["price_check"]


def _is_price_supported(price_text: str, compact_source: str) -> bool:
    compact_price = _compact_text(price_text)
    if not compact_source:
        return False
    if compact_price in compact_source:
        return True
    number = re.sub(r"[^\d.]", "", compact_price)
    return bool(number and f"{number}元" in compact_source)


def _guard_delivery_promises(reply: str) -> tuple[str, list[str]]:
    if DELIVERY_PROMISE_PATTERN.search(reply) is None:
        return reply, []
    guarded_reply = DELIVERY_PROMISE_PATTERN.sub("配送安排", reply)
    guarded_reply = _append_once(guarded_reply, DELIVERY_CONFIRMATION_TEXT)
    return guarded_reply, ["delivery_promise"]


def _guard_food_safety(reply: str) -> tuple[str, list[str]]:
    if not any(keyword in reply for keyword in FOOD_SAFETY_KEYWORDS):
        return reply, []
    return _append_once(reply, FOOD_SAFETY_NOTICE), ["food_safety"]


def _append_once(reply: str, sentence: str) -> str:
    if sentence in reply:
        return reply
    return f"{reply.rstrip()}\n{sentence}"


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


async def _record_guard_hit(
    context: ReplyGuardContext,
    hit_rules: list[str],
) -> None:
    try:
        await context.analytics_repo.add_event(
            session_id=context.session.id,
            buyer_id=context.user_id,
            event_type=REPLY_GUARD_EVENT_TYPE,
            event_source=REPLY_GUARD_EVENT_SOURCE,
            ref_id=context.session.id,
            meta_data=json.dumps(
                {
                    "rules": sorted(set(hit_rules)),
                    "channel": context.channel,
                },
                ensure_ascii=False,
            ),
            created_at=now_str(),
        )
    except Exception as exc:
        logger.warning("回复校验门埋点失败: %s", exc)
