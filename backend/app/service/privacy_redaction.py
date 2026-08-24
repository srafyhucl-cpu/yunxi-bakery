"""外发到模型前的结构化隐私脱敏。"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
OPEN_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])o[a-zA-Z0-9_-]{10,}")
ORDER_PATTERN = re.compile(
    r"((?:订单|订单号|order(?:_?no)?|单号)\s*[:：#]?\s*)[A-Za-z0-9_-]{6,}",
    re.IGNORECASE,
)
STANDALONE_ORDER_ID_PATTERN = re.compile(
    r"\b(?:ORD|ORDER)[-_A-Za-z0-9]{6,}\b",
    re.IGNORECASE,
)
ADDRESS_PATTERN = re.compile(
    r"(?:中国)?(?:北京|上海|天津|重庆|河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|海南|四川|贵州|云南|陕西|甘肃|青海|台湾|内蒙古|广西|西藏|宁夏|新疆|香港|澳门)"
    r"[^\n，,。；;]{0,40}(?:路|街|道|巷)[^\n，,。；;]{0,30}(?:号|栋|单元|室)",
)
REGION_ADDRESS_PATTERN = re.compile(
    r"(?:中国)?(?:北京|上海|天津|重庆|河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|海南|四川|贵州|云南|陕西|甘肃|青海|台湾|内蒙古|广西|西藏|宁夏|新疆|香港|澳门)"
    r"[^\n，,。；;]{2,80}(?:号|栋|单元|室|座|楼)",
)
PHONE_KEYS = frozenset(
    {"phone", "mobile", "receiver_phone", "contact_phone", "telephone"}
)
ADDRESS_KEYS = frozenset(
    {"address", "delivery_address", "receiver_address", "full_address"}
)
IDENTITY_KEYS = frozenset({"open_id", "openid", "user_id", "userid"})
ORDER_KEYS = frozenset(
    {"order_id", "order_no", "order_number", "trade_id", "trade_no", "tid"}
)
RAW_MESSAGE_KEYS = frozenset(
    {"raw_message", "original_message", "message_text", "history_text"}
)


def redact_external_text(text: str) -> str:
    """移除模型外发文本中的直接身份和履约定位字段。"""
    redacted = PHONE_PATTERN.sub("<手机号>", text)
    redacted = OPEN_ID_PATTERN.sub("<open_id>", redacted)
    redacted = ORDER_PATTERN.sub(r"\1<订单号>", redacted)
    redacted = STANDALONE_ORDER_ID_PATTERN.sub("<订单号>", redacted)
    redacted = ADDRESS_PATTERN.sub("<地址>", redacted)
    return REGION_ADDRESS_PATTERN.sub("<地址>", redacted)


def redact_external_messages(
    messages: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """递归脱敏模型请求消息，保留角色、工具和多模态结构。"""
    return [_redact_mapping(message) for message in messages]


def redact_external_langchain_messages(messages: Sequence[Any]) -> list[Any]:
    """脱敏 LangChain 消息并保留其标准消息类型。"""
    from langchain_core.messages import message_to_dict, messages_from_dict

    redacted_dicts = [_redact_mapping(message_to_dict(message)) for message in messages]
    return list(messages_from_dict(redacted_dicts))


def _redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _redact_keyed_value(key, item) for key, item in value.items()}


def _redact_keyed_value(key: str, value: Any) -> Any:
    normalized_key = key.strip().lower()
    if normalized_key in PHONE_KEYS:
        return "<手机号>"
    if normalized_key in ADDRESS_KEYS:
        return "<地址>"
    if normalized_key in IDENTITY_KEYS:
        return "<open_id>"
    if normalized_key in ORDER_KEYS:
        return "<订单号>"
    if normalized_key in RAW_MESSAGE_KEYS:
        return "<原始消息>"
    return _redact_value(value)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_external_text(value)
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_redact_value(item) for item in value]
    return value
