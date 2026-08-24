"""画像探针策略。

本模块只判断是否允许探针，不生成话术，也不主动接入热路径。
"""

import json

MAX_PROBES_PER_SESSION = 1

CLEAR_ORDER_SIGNALS = (
    "下单",
    "购买",
    "要这个",
    "就这个",
    "多少钱",
    "价格",
    "转人工",
    "人工客服",
    "真人",
)

LOW_PATIENCE_SIGNALS = (
    "快点",
    "算了",
    "不用了",
    "麻烦",
    "怎么还",
)


def can_offer_profile_probe(extra_info: str, user_content: str) -> bool:
    """判断当前会话是否还能进行一次服务型画像探针。"""
    if _probe_count(extra_info) >= MAX_PROBES_PER_SESSION:
        return False
    normalized = user_content.strip()
    if not normalized:
        return False
    return not _contains_any(normalized, CLEAR_ORDER_SIGNALS + LOW_PATIENCE_SIGNALS)


def mark_profile_probe_used(extra_info: str) -> str:
    """记录本会话已使用一次画像探针预算。"""
    payload = _load_extra(extra_info)
    payload["profile_probe_count"] = _probe_count(extra_info) + 1
    return json.dumps(payload, ensure_ascii=False)


def _probe_count(extra_info: str) -> int:
    payload = _load_extra(extra_info)
    value = payload.get("profile_probe_count", 0)
    return value if isinstance(value, int) and value > 0 else 0


def _contains_any(content: str, signals: tuple[str, ...]) -> bool:
    return any(signal in content for signal in signals)


def _load_extra(extra_info: str) -> dict:
    try:
        payload = json.loads(extra_info or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
