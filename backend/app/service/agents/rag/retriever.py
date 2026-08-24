"""LangChain 知识库 Retriever 适配器。"""

from collections.abc import Callable
from typing import Any

from app.models.knowledge import KnowledgeEntry
from app.service.agents.rag.documents import knowledge_entry_to_document
from app.service.agents.rag.query import RagQueryPlan, RagQueryVariant
from app.service.knowledge_retriever import KnowledgeRetriever


class LangChainKnowledgeRetriever:
    """把项目知识检索器包装成 LangChain Retriever。"""

    def __init__(
        self,
        knowledge_retriever: KnowledgeRetriever,
        limit: int = 8,
        query_planner: Callable[[str], RagQueryPlan] | None = None,
        document_reranker: Callable[[str, list[Any]], list[Any]] | None = None,
    ) -> None:
        self._knowledge_retriever = knowledge_retriever
        self._limit = limit
        self._query_planner = query_planner
        self._document_reranker = document_reranker

    def as_retriever(self) -> Any:
        """构造 LangChain BaseRetriever 实例。"""
        from langchain_core.retrievers import BaseRetriever

        outer = self

        class _Retriever(BaseRetriever):
            def _get_relevant_documents(
                self,
                query: str,
                *,
                run_manager: Any = None,
            ) -> list[Any]:
                msg = "同步 LangChain 知识检索未启用，请使用 async 调用"
                raise NotImplementedError(msg)

            async def _aget_relevant_documents(
                self,
                query: str,
                *,
                run_manager: Any = None,
            ) -> list[Any]:
                return await outer._retrieve_documents(query)

        return _Retriever()

    async def _retrieve_documents(self, query: str) -> list[Any]:
        plan = self._build_query_plan(query)
        documents: list[Any] = []
        seen_keys: set[str] = set()
        for variant_index, variant in enumerate(plan.variants):
            entries = await self._knowledge_retriever.search(
                variant.query,
                limit=self._limit,
            )
            for entry in entries:
                entry_key = _entry_key(entry)
                if entry_key in seen_keys:
                    continue
                documents.append(
                    knowledge_entry_to_document(
                        entry,
                        extra_metadata={
                            "original_query": plan.original_query,
                            "retrieval_query": variant.query,
                            "query_variant_index": variant_index,
                            "query_variant_reason": variant.reason,
                        },
                    )
                )
                seen_keys.add(entry_key)
                if self._document_reranker is None and len(documents) >= self._limit:
                    return documents
        if self._document_reranker is None:
            return documents
        return self._document_reranker(query, documents)[: self._limit]

    def _build_query_plan(self, query: str) -> RagQueryPlan:
        if self._query_planner is not None:
            plan = self._query_planner(query)
            if plan.variants:
                return plan
        return RagQueryPlan(
            original_query=query,
            variants=(RagQueryVariant(query=query, reason="original"),),
        )


def _entry_key(entry: KnowledgeEntry) -> str:
    if entry.id:
        return f"kb:{entry.id}"
    if entry.youzan_item_id:
        return f"youzan:{entry.youzan_item_id}"
    return f"title:{entry.title}"
