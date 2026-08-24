"""离线沉淀的高价值服务信号识别。"""

import re
from dataclasses import dataclass, field

from app.models.message import Message
from app.service.offline.agent_shared import role_text

MIN_GREETING_TURNS_FOR_STALL = 3
GREETING_STALL_ISSUE = "用户连续寒暄后才进入需求，需更快识别意图并引导到具体咨询"
GREETING_PREFIXES = ("你好", "您好", "在吗", "hello", "hi")
BIRTHDAY_OCCASION_PATTERNS = (
    "过生日",
    "生日蛋糕",
    "生日用",
    "生日宴",
    "生日惊喜",
    "妈妈生日",
    "爸爸生日",
    "孩子生日",
    "小孩生日",
    "宝宝生日",
    "女儿生日",
    "儿子生日",
    "老婆生日",
    "老公生日",
)
SPECIAL_DATE_PATTERNS = (
    ("给自己过生日", "birthday", "自己", "生日蛋糕"),
    ("自己过生日", "birthday", "自己", "生日蛋糕"),
    ("给妈妈过生日", "birthday", "妈妈", "生日蛋糕"),
    ("妈妈过生日", "birthday", "妈妈", "生日蛋糕"),
    ("妈妈生日", "birthday", "妈妈", "生日蛋糕"),
    ("给爸爸过生日", "birthday", "爸爸", "生日蛋糕"),
    ("爸爸过生日", "birthday", "爸爸", "生日蛋糕"),
    ("爸爸生日", "birthday", "爸爸", "生日蛋糕"),
    ("给孩子过生日", "birthday", "孩子", "儿童生日"),
    ("孩子过生日", "birthday", "孩子", "儿童生日"),
    ("孩子生日", "birthday", "孩子", "儿童生日"),
    ("给小朋友过生日", "birthday", "孩子", "儿童生日"),
    ("小朋友过生日", "birthday", "孩子", "儿童生日"),
    ("小朋友生日", "birthday", "孩子", "儿童生日"),
    ("给宝宝过生日", "birthday", "宝宝", "儿童生日"),
    ("宝宝过生日", "birthday", "宝宝", "儿童生日"),
    ("宝宝生日", "birthday", "宝宝", "儿童生日"),
    ("给女儿过生日", "birthday", "女儿", "生日蛋糕"),
    ("女儿过生日", "birthday", "女儿", "生日蛋糕"),
    ("女儿生日", "birthday", "女儿", "生日蛋糕"),
    ("给儿子过生日", "birthday", "儿子", "生日蛋糕"),
    ("儿子过生日", "birthday", "儿子", "生日蛋糕"),
    ("儿子生日", "birthday", "儿子", "生日蛋糕"),
    ("给老婆过生日", "birthday", "老婆", "生日蛋糕"),
    ("老婆过生日", "birthday", "老婆", "生日蛋糕"),
    ("老婆生日", "birthday", "老婆", "生日蛋糕"),
    ("给老公过生日", "birthday", "老公", "生日蛋糕"),
    ("老公过生日", "birthday", "老公", "生日蛋糕"),
    ("老公生日", "birthday", "老公", "生日蛋糕"),
    ("结婚纪念日", "anniversary", "夫妻", "结婚纪念日"),
    ("周年纪念", "anniversary", "夫妻", "周年纪念"),
    ("纪念日", "anniversary", "夫妻", "纪念日"),
)
DATE_PATTERN = re.compile(r"(?P<month>\d{1,2})月(?P<day>\d{1,2})(?:日|号)?")


@dataclass
class MemorySignal:
    """可直接写入顾客画像的服务事实。"""

    preferences: dict[str, object] = field(default_factory=dict)
    order_summary: dict[str, object] = field(default_factory=dict)
    allergens: list[str] = field(default_factory=list)
    special_dates: list[dict[str, object]] = field(default_factory=list)

    def has_fact(self) -> bool:
        return bool(
            self.preferences
            or self.order_summary
            or self.allergens
            or self.special_dates
        )


@dataclass
class GapSignal:
    """可进入知识缺口表的待审核问题。"""

    question_norm: str
    proposed_answer: str


def extract_memory_signal(messages: list[Message]) -> MemorySignal:
    """从真实对话中兜底抽取可服务事实。"""
    user_text = _joined_user_text(messages)
    signal = MemorySignal()
    _extract_audience_and_usage(user_text, signal)
    _extract_taste_and_diet(user_text, signal)
    _extract_product_interest(user_text, signal)
    _extract_special_dates(user_text, signal)
    return signal


def extract_review_issues(messages: list[Message]) -> list[str]:
    """从对话行为中提取可解释的质检问题。"""
    dialog_text = _joined_dialog_text(messages)
    issues: list[str] = []
    if "转人工" in dialog_text or "人工客服" in dialog_text:
        issues.append("用户要求转人工，需复核机器人是否已充分解决前置问题")
    if "为什么不发卡片" in dialog_text or "有图片吗" in dialog_text:
        issues.append("用户关注图片或商品卡片，需复核卡片是否成功触达")
    if "不适合老人" in dialog_text:
        issues.append("推荐结果被用户指出不适合老人，需优化长辈场景推荐规则")
    if "不可以哦" in dialog_text or "这个不行" in dialog_text:
        issues.append("人工客服纠正了机器人未能明确处理的问题，需沉淀规则")
    _extract_greeting_stall_issue(messages, issues)
    return _unique_texts(issues)


def extract_gap_signals(messages: list[Message]) -> list[GapSignal]:
    """从会话中提取无需依赖模型的知识缺口候选。"""
    dialog_text = _joined_dialog_text(messages)
    gaps: list[GapSignal] = []
    if "娃娃头" in dialog_text and "4寸" in dialog_text:
        gaps.append(
            GapSignal(
                question_norm="娃娃头水果奶油蛋糕是否支持4寸定制",
                proposed_answer="需人工审核后补充：娃娃头水果奶油蛋糕是否支持4寸，以及不可定制时可替代的4寸儿童蛋糕款式。",
            )
        )
    if "老人" in dialog_text and (
        "木糖醇" in dialog_text or "不适合老人" in dialog_text
    ):
        gaps.append(
            GapSignal(
                question_norm="老人木糖醇蛋糕应该如何推荐",
                proposed_answer="需人工审核后补充：长辈或老人场景优先推荐低糖、祝寿或稳重造型蛋糕，避免推荐明显年轻化造型。",
            )
        )
    if "为什么不发卡片" in dialog_text or "有图片吗" in dialog_text:
        gaps.append(
            GapSignal(
                question_norm="用户要求图片时商品卡片未成功触达应如何处理",
                proposed_answer="需人工审核后补充：当用户要图片或反馈未收到卡片时，客服应确认卡片发送状态，并提供可点击商品链接或转人工。",
            )
        )
    if "现在订蛋糕需要等多久" in dialog_text or "急单" in dialog_text:
        gaps.append(
            GapSignal(
                question_norm="临近截单时间的急单等待时间如何答复",
                proposed_answer="需人工审核后补充：临近每日截单时间时，急单需提示人工确认产能、配送和取货时间，避免直接承诺。",
            )
        )
    if "拉布布" in dialog_text or "Labubu" in dialog_text:
        gaps.append(
            GapSignal(
                question_norm="Labubu定制蛋糕是否支持按图定制及价格提前期",
                proposed_answer="需人工审核后补充：Labubu定制蛋糕的价格、提前预订时间、是否支持按图定制和下单确认流程。",
            )
        )
    return _unique_gaps(gaps)


def _extract_audience_and_usage(user_text: str, signal: MemorySignal) -> None:
    if "孩子" in user_text or "小孩" in user_text or "小朋友" in user_text:
        signal.preferences["audience"] = "孩子"
        signal.order_summary["usage"] = "儿童蛋糕"
    if "老人" in user_text or "长辈" in user_text:
        signal.preferences["audience"] = "老人"
        signal.order_summary["usage"] = "长辈蛋糕"
    if "聚会" in user_text:
        signal.order_summary["usage"] = "聚会"
    if _has_birthday_occasion(user_text):
        signal.order_summary["occasion"] = "生日"


def _extract_taste_and_diet(user_text: str, signal: MemorySignal) -> None:
    if "不要太甜" in user_text or "少糖" in user_text or "低甜" in user_text:
        signal.preferences["sweetness"] = "低甜"
    if "木糖醇" in user_text:
        signal.preferences["sweetness"] = "木糖醇"


def _extract_product_interest(user_text: str, signal: MemorySignal) -> None:
    interests: list[str] = []
    if "荔枝" in user_text:
        interests.append("荔枝口味")
    if "赛车" in user_text:
        interests.append("赛车主题")
    if "拉布布" in user_text or "Labubu" in user_text:
        interests.append("Labubu定制")
    if "4寸" in user_text or "4存" in user_text:
        signal.preferences["size_interest"] = "4寸"
    if "定制" in user_text:
        signal.preferences["service_interest"] = "定制蛋糕"
    if interests:
        signal.preferences["product_interests"] = _unique_texts(interests)


def _extract_special_dates(user_text: str, signal: MemorySignal) -> None:
    date_text = _extract_month_day(user_text)
    for pattern, event_type, person, usage in SPECIAL_DATE_PATTERNS:
        if pattern not in user_text:
            continue
        signal.special_dates.append(
            {
                "type": event_type,
                "person": person,
                "date": date_text,
                "date_known": bool(date_text),
                "usage": usage,
                "evidence": user_text,
            }
        )


def _extract_month_day(user_text: str) -> str:
    match = DATE_PATTERN.search(user_text)
    if match is None:
        return ""
    month = int(match.group("month"))
    day = int(match.group("day"))
    return f"{month:02d}-{day:02d}"


def _joined_user_text(messages: list[Message]) -> str:
    return "\n".join(
        message.content for message in messages if _is_user_message(message)
    )


def _joined_dialog_text(messages: list[Message]) -> str:
    return "\n".join(message.content for message in messages)


def _extract_greeting_stall_issue(messages: list[Message], issues: list[str]) -> None:
    if _count_leading_greetings(messages) >= MIN_GREETING_TURNS_FOR_STALL:
        issues.append(GREETING_STALL_ISSUE)


def _count_leading_greetings(messages: list[Message]) -> int:
    count = 0
    for message in messages:
        if not _is_user_message(message):
            continue
        if _is_greeting_turn(message.content):
            count += 1
            continue
        break
    return count


def _is_greeting_turn(content: str) -> bool:
    normalized = _normalize_dialog_turn(content)
    if len(normalized) > 6:
        return False
    return any(normalized.startswith(prefix) for prefix in GREETING_PREFIXES)


def _normalize_dialog_turn(content: str) -> str:
    normalized = content.lower()
    for marker in ("[语音]", "[文本]", "think>", "<chinese>"):
        normalized = normalized.replace(marker, "")
    normalized = normalized.strip()
    return "".join(
        char for char in normalized if char.isalnum() or "\u4e00" <= char <= "\u9fff"
    )


def _is_user_message(message: Message) -> bool:
    return role_text(message.role) == "user"


def _has_birthday_occasion(user_text: str) -> bool:
    return any(pattern in user_text for pattern in BIRTHDAY_OCCASION_PATTERNS)


def _unique_texts(items: list[str]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        if item in seen:
            continue
        values.append(item)
        seen.add(item)
    return values


def _unique_gaps(gaps: list[GapSignal]) -> list[GapSignal]:
    seen: set[str] = set()
    values: list[GapSignal] = []
    for gap in gaps:
        if gap.question_norm in seen:
            continue
        values.append(gap)
        seen.add(gap.question_norm)
    return values
