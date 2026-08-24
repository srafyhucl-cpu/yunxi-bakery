"""
消息数据模型。

一条消息对应 LLM 会话中的一次交互（user / assistant / tool）。
tool 类型的消息记录 Function Calling 的调用和结果。
"""

from dataclasses import dataclass
from enum import Enum


class MessageRole(str, Enum):
    """消息角色：用户 / AI / 系统指令 / 工具调用结果"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class Message:
    """对话中的一条消息。"""

    id: str
    session_id: str
    role: MessageRole
    content: str
    channel_msg_id: str = ""  # 渠道原始消息ID（用于去重）
    estimated_tokens: int = 0  # 预估 token 数（用于滑动窗口裁切）
    tool_calls: str = "[]"  # JSON: LLM 发起的工具调用
    tool_name: str = ""  # 工具名称（role=tool 时使用）
    created_at: str = ""
