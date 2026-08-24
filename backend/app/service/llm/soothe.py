"""
安抚策略。

当用户表达不满/投诉/催单时，在正式回答前附加安抚话术。
旨在第一时间化解顾客负面情绪，避免冲突升级。
"""

SOOTHE_KEYWORDS: list[str] = [
    "投诉",
    "退款",
    "坏了",
    "塌了",
    "碰坏",
    "漏了",
    "少发",
    "超时",
    "不满意",
    "太差",
    "垃圾",
    "差劲",
    "坑人",
    "骗子",
    "找你们领导",
    "找店长",
    "找老板",
    "投诉你们",
    "怎么还没到",
    "等了多久",
    "催单",
    "退钱",
]

SOOTHE_PREFIX = "非常抱歉给您带来不好的体验，"


def needs_soothe(text: str) -> bool:
    """检测用户消息是否包含需要安抚的敏感词。"""
    return any(kw in text for kw in SOOTHE_KEYWORDS)


def apply_soothe(reply: str) -> str:
    """给回复加安抚前缀（如果还没含道歉语）。"""
    if any(w in reply for w in ["抱歉", "对不起", "不好意思", "非常抱歉"]):
        return reply
    return SOOTHE_PREFIX + reply
