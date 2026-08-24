"""知识配置后台相关的数据模型。"""

from dataclasses import dataclass

from app.models.knowledge import KnowledgeContentType


@dataclass
class KnowledgeAdminDraft:
    """后台表单提交的知识条目草稿。"""

    title: str
    content: str
    content_type: str
    keywords: str = ""
    priority: int = 50
    is_active: bool = True
    audience: str = "all"
    review_status: str = "published"
    valid_from: str = ""
    valid_until: str = ""


@dataclass
class KnowledgeCategorySuggestion:
    """系统给出的知识分类建议。"""

    content_type: str = KnowledgeContentType.FAQ
    label: str = "常见问答"
    reason: str = ""
