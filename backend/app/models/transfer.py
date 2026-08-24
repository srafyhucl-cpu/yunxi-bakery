"""
转人工数据模型。

记录客户从请求转人工到客服处理完成的完整生命周期。
"""

from dataclasses import dataclass
from enum import Enum


class TransferStatus(str, Enum):
    """转人工状态：等待接单 / 已接入 / 已拒绝 / 已结束"""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CLOSED = "closed"


@dataclass
class HumanTransfer:
    """一条转人工工单。"""

    id: str
    session_id: str
    user_id: str
    staff_id: str = ""  # 接单客服ID
    reason: str = ""  # 转人工原因
    status: TransferStatus = TransferStatus.PENDING
    conversation_summary: str = ""  # 转接时的对话摘要，供客服快速了解上下文
    created_at: str = ""
    accepted_at: str = ""  # 客服接单时间
    closed_at: str = ""  # 结束时间
