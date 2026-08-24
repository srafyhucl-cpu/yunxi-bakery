"""知识缺口建议数据模型。"""

from dataclasses import dataclass
from enum import Enum


class KnowledgeGapStatus(str, Enum):
    """知识缺口处理状态。"""

    OPEN = "open"
    PROPOSED = "proposed"
    RESOLVED = "resolved"
    REJECTED = "rejected"


@dataclass
class KnowledgeGap:
    """一条知识缺口建议。"""

    id: int
    question_norm: str
    frequency: int = 1
    status: str = KnowledgeGapStatus.OPEN.value
    proposed_answer: str = ""
    related_sessions_json: str = "[]"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class KnowledgeGapCreate:
    """创建知识缺口建议所需参数。"""

    question_norm: str
    frequency: int = 1
    status: str = KnowledgeGapStatus.OPEN.value
    proposed_answer: str = ""
    related_sessions_json: str = "[]"
