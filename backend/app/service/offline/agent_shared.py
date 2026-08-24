"""离线 Agent 共享工具。"""

from app.models.message import Message


def format_dialog(messages: list[Message]) -> str:
    """把会话消息压缩成离线 Agent 可读的纯文本。"""
    lines = [f"{role_text(message.role)}: {message.content}" for message in messages]
    return "\n".join(lines)[-6000:]


def role_text(role: object) -> str:
    """兼容模型枚举和数据库读回的字符串角色。"""
    return getattr(role, "value", str(role))
