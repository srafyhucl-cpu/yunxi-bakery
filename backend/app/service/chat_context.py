"""ChatService 的知识上下文与 LLM 消息构造边界。"""

import time
from dataclasses import dataclass

from app.logger import setup_logger
from app.config import settings
from app.models.customer_profile import CustomerProfile
from app.models.knowledge import KnowledgeEntry
from app.models.session import Session
from app.service.agents.rag.documents import document_to_knowledge_entry
from app.service.agents.rag.modes import build_langchain_knowledge_retriever_for_mode
from app.service.chat_context_budget import (
    ChatContextBudgetSnapshot,
    build_chat_context_budget_snapshot,
)
from app.service.chat_intent import build_history_text
from app.service.chat_multimodal import apply_multimodal_image_message
from app.service.knowledge_retriever import KnowledgeRetriever
from app.service.agents.customer.prompts import (
    build_customer_context_messages,
    build_customer_system_prompt,
    build_guard_source_text,
    extract_product_titles,
)
from app.service.llm.intent import IntentType
from app.service.llm.query_rewriter import rewrite_query
from app.service.session_manager import SessionManager

logger = setup_logger()

DEFAULT_SEARCH_QUERY = "芸熙烘焙 产品 价格"
KNOWLEDGE_SEARCH_LIMIT = 8


@dataclass(frozen=True)
class ChatContext:
    messages: list[dict]
    rag_ms: int
    product_titles: tuple[str, ...] = ()
    knowledge_entry_ids: tuple[int, ...] = ()
    guard_source_text: str = ""
    context_budget: ChatContextBudgetSnapshot | None = None


async def prepare_ai_conversation_messages(
    session_mgr: SessionManager,
    knowledge: KnowledgeRetriever,
    session: Session,
    user_query: str,
    intent: IntentType,
    timing: dict | None,
    history: list[dict] | None,
    history_text: str,
    image_base64: str | None,
    customer_profile: CustomerProfile | None = None,
    conversation_summary_text: str = "",
) -> tuple[list[dict], str]:
    if history is None:
        history = await session_mgr.build_context(session.id)
        history_text = build_history_text(history)
    chat_context = await prepare_chat_context(
        knowledge=knowledge,
        user_query=user_query,
        history_text=history_text,
        intent=intent,
        history=history,
        customer_profile=customer_profile,
        conversation_summary_text=conversation_summary_text,
    )
    if timing is not None:
        timing["rag_ms"] = chat_context.rag_ms
        timing["guard_product_titles"] = list(chat_context.product_titles)
        timing["guard_source_text"] = chat_context.guard_source_text
        timing["knowledge_entry_ids"] = list(chat_context.knowledge_entry_ids)
        if chat_context.context_budget is not None:
            timing["context_budget"] = chat_context.context_budget.to_dict()
    messages = chat_context.messages

    if image_base64:
        apply_multimodal_image_message(messages, image_base64, session.id)

    return messages, history_text


async def prepare_chat_context(
    knowledge: KnowledgeRetriever,
    user_query: str,
    history_text: str,
    intent: IntentType,
    history: list[dict],
    customer_profile: CustomerProfile | None = None,
    conversation_summary_text: str = "",
) -> ChatContext:
    started_at = time.monotonic()
    knowledge_entries = await load_knowledge_entries(
        knowledge=knowledge,
        user_query=user_query,
        history_text=history_text,
        intent=intent,
    )
    system_prompt = build_customer_system_prompt(
        knowledge_entries,
        customer_profile,
        conversation_summary_text,
    )
    messages = build_customer_context_messages(system_prompt, history)
    return ChatContext(
        messages=messages,
        rag_ms=round((time.monotonic() - started_at) * 1000),
        product_titles=extract_product_titles(knowledge_entries),
        knowledge_entry_ids=tuple(entry.id for entry in knowledge_entries),
        guard_source_text=build_guard_source_text(knowledge_entries),
        context_budget=build_chat_context_budget_snapshot(
            system_prompt=system_prompt,
            history=history,
            knowledge_entries=knowledge_entries,
            knowledge_entry_limit=KNOWLEDGE_SEARCH_LIMIT,
            customer_profile=customer_profile,
            conversation_summary_text=conversation_summary_text,
        ),
    )


async def load_knowledge_entries(
    knowledge: KnowledgeRetriever,
    user_query: str,
    history_text: str,
    intent: IntentType,
) -> list[KnowledgeEntry]:
    if intent == IntentType.SMALL_TALK:
        return await knowledge.search_keyword_only(
            user_query, limit=KNOWLEDGE_SEARCH_LIMIT
        )

    search_query = user_query or DEFAULT_SEARCH_QUERY
    rewritten = await rewrite_query(search_query, history=history_text)
    try:
        return await _search_knowledge_with_configured_mode(knowledge, rewritten)
    except Exception as exc:
        logger.error("知识库检索失败，使用空上下文继续: %s", exc)
        return []


async def _search_knowledge_with_configured_mode(
    knowledge: KnowledgeRetriever,
    query: str,
) -> list[KnowledgeEntry]:
    retriever = build_langchain_knowledge_retriever_for_mode(
        knowledge,
        mode=settings.RAG_RETRIEVAL_MODE,
        limit=KNOWLEDGE_SEARCH_LIMIT,
    ).as_retriever()
    documents = await retriever.ainvoke(query)
    return [document_to_knowledge_entry(document) for document in documents]
