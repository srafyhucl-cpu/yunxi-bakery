"""RAG 检索模式策略。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.config import (
    RAG_RETRIEVAL_MODE_HYBRID,
    RAG_RETRIEVAL_MODE_PLANNED_HYBRID,
    RAG_RETRIEVAL_MODE_PLANNED_HYBRID_RERANK,
)
from app.service.agents.rag.query import RagQueryPlan, build_customer_rag_query_plan
from app.service.agents.rag.rerank import rerank_documents_by_query_rules
from app.service.agents.rag.retriever import LangChainKnowledgeRetriever
from app.service.knowledge_retriever import KnowledgeRetriever


@dataclass(frozen=True)
class RagRetrievalModeStrategy:
    """RAG 检索模式对应的策略组件。"""

    mode: str
    query_planner: Callable[[str], RagQueryPlan] | None = None
    document_reranker: Callable[[str, list[Any]], list[Any]] | None = None

    @property
    def uses_query_planning(self) -> bool:
        return self.query_planner is not None

    @property
    def uses_rerank(self) -> bool:
        return self.document_reranker is not None


def resolve_rag_retrieval_mode_strategy(mode: str) -> RagRetrievalModeStrategy:
    """把配置中的 RAG 检索模式解析为只读策略。"""
    normalized_mode = mode.strip().lower()
    if normalized_mode == RAG_RETRIEVAL_MODE_HYBRID:
        return RagRetrievalModeStrategy(mode=RAG_RETRIEVAL_MODE_HYBRID)
    if normalized_mode == RAG_RETRIEVAL_MODE_PLANNED_HYBRID:
        return RagRetrievalModeStrategy(
            mode=RAG_RETRIEVAL_MODE_PLANNED_HYBRID,
            query_planner=build_customer_rag_query_plan,
        )
    if normalized_mode == RAG_RETRIEVAL_MODE_PLANNED_HYBRID_RERANK:
        return RagRetrievalModeStrategy(
            mode=RAG_RETRIEVAL_MODE_PLANNED_HYBRID_RERANK,
            query_planner=build_customer_rag_query_plan,
            document_reranker=rerank_documents_by_query_rules,
        )
    msg = f"未知 RAG 检索模式: {mode}"
    raise ValueError(msg)


def build_langchain_knowledge_retriever_for_mode(
    knowledge_retriever: KnowledgeRetriever,
    *,
    mode: str,
    limit: int = 8,
) -> LangChainKnowledgeRetriever:
    """按配置模式构造 LangChain 知识检索 adapter。"""
    strategy = resolve_rag_retrieval_mode_strategy(mode)
    return LangChainKnowledgeRetriever(
        knowledge_retriever,
        limit=limit,
        query_planner=strategy.query_planner,
        document_reranker=strategy.document_reranker,
    )
