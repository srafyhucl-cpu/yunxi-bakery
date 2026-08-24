"""企微智能机器人 API 模式消息结构。"""

from __future__ import annotations

import re
from typing import Any

MSGTYPE_TEXT = "text"
MSGTYPE_STREAM = "stream"
MSGTYPE_EVENT = "event"
MSGTYPE_MIXED = "mixed"
MSGTYPE_VOICE = "voice"
MENTION_PREFIX_PATTERN = re.compile(r"@\S+\s*")


def extract_message_text(message: dict[str, Any]) -> str:
    """从智能机器人回调明文 JSON 中提取员工文本。"""
    msgtype = str(message.get("msgtype") or "")
    if msgtype == MSGTYPE_TEXT:
        return _clean_message_text(_nested_content(message, MSGTYPE_TEXT))
    if msgtype == MSGTYPE_VOICE:
        return _clean_message_text(_nested_content(message, MSGTYPE_VOICE))
    if msgtype == MSGTYPE_MIXED:
        return _clean_message_text(_mixed_text(message))
    return ""


def is_message_callback(message: dict[str, Any]) -> bool:
    """判断是否为可回复的用户消息回调。"""
    msgtype = str(message.get("msgtype") or "")
    return msgtype in {MSGTYPE_TEXT, MSGTYPE_MIXED, MSGTYPE_VOICE}


def build_text_reply(content: str) -> dict[str, Any]:
    """构造智能机器人被动文本回复明文。"""
    return {
        "msgtype": MSGTYPE_TEXT,
        "text": {"content": content},
    }


def build_stream_reply(
    stream_id: str,
    content: str,
    *,
    finish: bool,
) -> dict[str, Any]:
    """构造智能机器人流式回复明文。"""
    return {
        "msgtype": MSGTYPE_STREAM,
        "stream": {
            "id": stream_id,
            "finish": finish,
            "content": content,
        },
    }


def _nested_content(message: dict[str, Any], key: str) -> str:
    value = message.get(key)
    if not isinstance(value, dict):
        return ""
    content = value.get("content") or value.get("text")
    return content.strip() if isinstance(content, str) else ""


def _mixed_text(message: dict[str, Any]) -> str:
    mixed = message.get(MSGTYPE_MIXED)
    if not isinstance(mixed, dict):
        return ""
    items = mixed.get("msg_item")
    if not isinstance(items, list):
        return ""
    text_parts = [
        _nested_content(item, MSGTYPE_TEXT)
        for item in items
        if isinstance(item, dict) and item.get("msgtype") == MSGTYPE_TEXT
    ]
    return "\n".join(part for part in text_parts if part)


def _clean_message_text(content: str) -> str:
    return MENTION_PREFIX_PATTERN.sub("", content).strip()
