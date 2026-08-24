"""LangChain 消息转换工具。"""

from collections.abc import Mapping, Sequence
from typing import Any


def to_langchain_messages(messages: Sequence[Any]) -> list[Any]:
    """把消息输入转换为 LangChain 消息，已是标准消息时保持原对象。"""
    from langchain_core.messages import BaseMessage, convert_to_messages

    if all(isinstance(message, BaseMessage) for message in messages):
        return list(messages)
    return list(convert_to_messages(messages))


def message_role(message: Any) -> str:
    """读取 LangChain 消息或 OpenAI 字典的角色。"""
    if isinstance(message, Mapping):
        return str(message.get("role", ""))
    return str(getattr(message, "type", ""))


def message_content(message: Any) -> Any:
    """读取 LangChain 消息或 OpenAI 字典的内容。"""
    if isinstance(message, Mapping):
        return message.get("content", "")
    return getattr(message, "content", "")


def message_tool_calls(message: Any) -> list[dict[str, Any]]:
    """读取 LangChain 消息或 OpenAI 字典的工具调用。"""
    if isinstance(message, Mapping):
        tool_calls = message.get("tool_calls") or []
    else:
        tool_calls = getattr(message, "tool_calls", None) or []
    return [call for call in tool_calls if isinstance(call, dict)]
