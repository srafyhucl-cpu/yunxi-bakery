"""知识库检索命中日志模型。"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KnowledgeRetrievalLogCreate:
    bot_type: str
    audience: str
    query: str
    retrieval_mode: str
    matched_entry_ids: list[int] = field(default_factory=list)
    matched_titles: list[str] = field(default_factory=list)
    result_count: int = 0
    fallback_reason: str = ""
    query_hash: str = ""
    query_category: str = ""


@dataclass(frozen=True)
class KnowledgeRetrievalLog:
    id: int
    bot_type: str
    audience: str
    query: str
    retrieval_mode: str
    matched_entry_ids_json: str
    matched_titles_json: str
    result_count: int
    fallback_reason: str
    created_at: str
    query_hash: str = ""
    query_category: str = ""
