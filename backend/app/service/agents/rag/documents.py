"""知识条目与 LangChain Document 转换。"""

from typing import Any, cast

from app.models.knowledge import KnowledgeCategory, KnowledgeEntry


def knowledge_entry_to_document(
    entry: KnowledgeEntry,
    extra_metadata: dict[str, Any] | None = None,
) -> Any:
    """把知识条目转换为 LangChain Document。"""
    from langchain_core.documents import Document

    metadata = {
        "knowledge_id": entry.id,
        "title": entry.title,
        "category": str(entry.category),
        "content_type": str(entry.content_type),
        "audience": entry.audience,
        "review_status": entry.review_status,
        "youzan_item_id": entry.youzan_item_id or "",
        "priority": entry.priority,
        "valid_from": entry.valid_from,
        "valid_until": entry.valid_until,
        "last_sync_source": entry.last_sync_source,
        "last_sync_ref": entry.last_sync_ref,
    }
    metadata.update(extra_metadata or {})
    return Document(
        page_content=entry.content,
        metadata=metadata,
    )


def knowledge_entries_to_documents(
    entries: list[KnowledgeEntry],
    extra_metadata: dict[str, Any] | None = None,
) -> list[Any]:
    """批量转换知识条目。"""
    return [
        knowledge_entry_to_document(entry, extra_metadata=extra_metadata)
        for entry in entries
    ]


def document_to_knowledge_entry(document: Any) -> KnowledgeEntry:
    """把 LangChain Document 还原为现有知识上下文模型。"""
    metadata = dict(getattr(document, "metadata", {}) or {})
    return KnowledgeEntry(
        id=_metadata_int(metadata, "knowledge_id"),
        title=str(metadata.get("title") or ""),
        content=str(getattr(document, "page_content", "") or ""),
        category=cast(
            KnowledgeCategory,
            str(metadata.get("category") or ""),
        ),
        content_type=str(metadata.get("content_type") or ""),
        audience=str(metadata.get("audience") or ""),
        review_status=str(metadata.get("review_status") or ""),
        youzan_item_id=str(metadata.get("youzan_item_id") or "") or None,
        priority=_metadata_int(metadata, "priority"),
        valid_from=str(metadata.get("valid_from") or ""),
        valid_until=str(metadata.get("valid_until") or ""),
        last_sync_source=str(metadata.get("last_sync_source") or ""),
        last_sync_ref=str(metadata.get("last_sync_ref") or ""),
    )


def _metadata_int(metadata: dict[str, Any], key: str) -> int:
    value = metadata.get(key)
    if value in (None, ""):
        return 0
    return int(value or 0)
