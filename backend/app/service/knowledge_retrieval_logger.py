"""知识库检索命中日志写入服务。"""

import hashlib

from app.logger import setup_logger
from app.models.knowledge import KnowledgeAudience, KnowledgeEntry
from app.models.knowledge_retrieval_log import KnowledgeRetrievalLogCreate
from app.repository.knowledge_repo import KnowledgeRepo
from app.service.privacy_redaction import redact_external_text

logger = setup_logger()

RETRIEVAL_MODE_HYBRID = "hybrid"
RETRIEVAL_MODE_VECTOR_KEYWORD = "vector_keyword"
RETRIEVAL_MODE_KEYWORD_ONLY = "keyword_only"
FALLBACK_REASON_NO_MATCH = "no_match"


def hash_retrieval_query(query: str) -> str:
    """只对脱敏后的检索词生成稳定摘要，不保存原始检索词。"""
    redacted_query = redact_external_text(query).strip()
    return hashlib.sha256(redacted_query.encode("utf-8")).hexdigest()


def classify_retrieval_query(query: str) -> str:
    """把检索词归入低敏类别，避免用原文做观测维度。"""
    normalized = query.strip().lower()
    if not normalized:
        return "empty"
    for category, keywords in {
        "order": ("订单", "物流", "order", "快递"),
        "product": ("蛋糕", "产品", "商品", "口味"),
        "policy": ("退款", "配送", "售后", "规则"),
    }.items():
        if any(keyword in normalized for keyword in keywords):
            return category
    return "other"


async def record_knowledge_retrieval_log(
    repo: KnowledgeRepo,
    *,
    bot_type: str,
    audience: str,
    query: str,
    retrieval_mode: str,
    entries: list[KnowledgeEntry],
) -> None:
    """记录一次知识检索命中，失败不影响在线检索。"""
    log_entry = KnowledgeRetrievalLogCreate(
        bot_type=bot_type,
        audience=audience,
        query=query,
        query_hash=hash_retrieval_query(query),
        query_category=classify_retrieval_query(query),
        retrieval_mode=retrieval_mode,
        matched_entry_ids=[entry.id for entry in entries if entry.id],
        matched_titles=[entry.title for entry in entries if entry.title],
        result_count=len(entries),
        fallback_reason="" if entries else FALLBACK_REASON_NO_MATCH,
    )
    try:
        await repo.insert_retrieval_log(log_entry)
    except Exception as exc:
        logger.warning("知识检索命中日志写入失败: %s", exc)


def bot_type_from_audience(audience: str) -> str:
    if audience == KnowledgeAudience.CUSTOMER.value:
        return "customer"
    if audience == KnowledgeAudience.EMPLOYEE.value:
        return "employee"
    return "shared"
