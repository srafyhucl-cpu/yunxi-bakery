"""离线会话质检数据模型。"""

from dataclasses import dataclass


@dataclass
class ConversationReview:
    """一条离线会话质检结果。"""

    id: int
    session_id: str
    quality_score: int
    issues_json: str = "[]"
    reviewer_model: str = ""
    reviewed_at: str = ""


@dataclass
class ConversationReviewCreate:
    """创建离线会话质检结果所需参数。"""

    session_id: str
    quality_score: int
    issues_json: str = "[]"
    reviewer_model: str = ""
    reviewed_at: str = ""
