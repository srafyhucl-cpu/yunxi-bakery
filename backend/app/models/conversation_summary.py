"""客户会话短期摘要数据模型。"""

from dataclasses import dataclass
from enum import Enum


class ConversationSummaryStatus(str, Enum):
    """会话摘要状态。"""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DISCARDED = "discarded"


@dataclass
class ConversationSummary:
    """一条客户会话短期摘要。"""

    id: str
    session_id: str
    channel: str
    user_id: str
    summary_text: str
    state_json: str = "{}"
    source_message_ids_json: str = "[]"
    source_until_message_id: str = ""
    token_estimate: int = 0
    status: str = ConversationSummaryStatus.ACTIVE.value
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ConversationSummaryCreate:
    """创建客户会话短期摘要所需参数。"""

    session_id: str
    channel: str
    user_id: str
    summary_text: str
    state_json: str = "{}"
    source_message_ids_json: str = "[]"
    source_until_message_id: str = ""
    token_estimate: int = 0
