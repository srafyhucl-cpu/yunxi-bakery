"""
会话数据模型。

一条会话记录一个客户从首次联系到结束的全过程。
状态流转: active → transfer_pending → human_service → closed
"""

from dataclasses import dataclass
from enum import Enum


class Channel(str, Enum):
    """渠道标识：所有合法渠道值的唯一来源"""

    YOUZAN = "youzan"
    WECOM_1ON1 = "wecom_1on1"
    WECOM_GROUP = "wecom_group"


class SessionStatus(str, Enum):
    """会话状态：AI 接待 / 转人工排队 / 人工服务中 / 已结束"""

    ACTIVE = "active"
    TRANSFER_PENDING = "transfer_pending"
    HUMAN_SERVICE = "human_service"
    CLOSED = "closed"


@dataclass
class Session:
    """一条完整的会话记录。"""

    id: str
    channel: str  # 取值见 Channel 枚举
    user_id: str  # 渠道用户ID（buyer_id / external_userid）
    staff_id: str = ""  # 当前负责的客服/员工ID
    status: SessionStatus = SessionStatus.ACTIVE
    extra_info: str = "{}"  # JSON 扩展字段
    created_at: str = ""
    updated_at: str = ""


@dataclass
class SessionCreate:
    """创建会话所需的参数。"""

    id: str
    channel: str
    user_id: str
    staff_id: str = ""
