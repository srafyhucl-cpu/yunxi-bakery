"""
知识库检索服务。

支持两种模式：
- 语义向量搜索（EmbeddingSearcher）：语义理解，模糊匹配
- 关键词搜索（SQL LIKE）：精确匹配

调用顺序：向量搜索 → 不够时补充关键词结果。
向量搜索通过 asyncio.to_thread 包裹，不阻塞事件循环。
"""

import asyncio
from app.logger import setup_logger
from app.models.config import FEATURED_PRODUCTS_KEY
from app.models.knowledge import KnowledgeAudience, KnowledgeEntry
from app.repository.config_repo import ConfigRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.bm25_search import BM25Searcher
from app.service.embedding_search import EmbeddingSearcher
from app.service.knowledge_live_data import (
    filter_recommendable_featured_products,
    prepend_live_data,
)
from app.service.knowledge_retrieval_logger import (
    RETRIEVAL_MODE_HYBRID,
    RETRIEVAL_MODE_KEYWORD_ONLY,
    RETRIEVAL_MODE_VECTOR_KEYWORD,
    bot_type_from_audience,
    record_knowledge_retrieval_log,
)
from app.service.retrieval_fusion import DEFAULT_RRF_K, fuse_ranked_results
from app.config import settings

logger = setup_logger()


class KnowledgeRetriever:
    """知识检索器：向量搜索 + 关键词搜索组合，并优先注入可售主推款。"""

    def __init__(
        self,
        repo: KnowledgeRepo,
        vs: EmbeddingSearcher | None = None,
        config_repo: ConfigRepo | None = None,
        bm25: BM25Searcher | None = None,
        enable_hybrid_retrieval: bool | None = None,
        rrf_k: int | None = None,
        audience: str = KnowledgeAudience.ALL.value,
        bot_type: str = "",
        youzan_product_repo: YouzanProductRepo | None = None,
    ) -> None:
        self._repo = repo
        self._vs = vs
        self._config_repo = config_repo
        self._bm25 = bm25
        self._audience = audience
        self._bot_type = bot_type or bot_type_from_audience(audience)
        self._youzan_product_repo = youzan_product_repo
        self._enable_hybrid_retrieval = (
            settings.ENABLE_HYBRID_RETRIEVAL
            if enable_hybrid_retrieval is None
            else enable_hybrid_retrieval
        )
        self._rrf_k = settings.RRF_K if rrf_k is None else rrf_k

    @property
    def embedding_searcher(self) -> EmbeddingSearcher | None:
        """返回用于增量向量同步的检索器。"""
        return self._vs

    async def search(self, query: str, limit: int = 8) -> list[KnowledgeEntry]:
        """
        混合检索：优先向量，不足时补关键词。

        参数：
            query: 用户查询文本
            limit: 返回最大条数
        返回：
            匹配的知识条目列表
        """
        if not query.strip():
            return []

        if self._enable_hybrid_retrieval:
            hybrid_results = await self._search_hybrid(query, limit)
            if hybrid_results:
                results = await self._inject_featured(hybrid_results, limit)
                final_results = await self._prepend_live_data(results)
                await self._record_retrieval_log(
                    query, RETRIEVAL_MODE_HYBRID, final_results
                )
                return final_results

        entries: list[KnowledgeEntry] = []
        if self._vs and self._vs.doc_count > 0:
            vs_results = await asyncio.to_thread(self._vs.search, query, limit)
            if vs_results:
                keys = [k for k, _ in vs_results]
                entries = await self._repo.get_by_youzan_item_ids(
                    keys, limit=len(keys), audience=self._audience
                )
                logger.debug("向量检索 '%s' → %d 条", query[:30], len(entries))

        keyword_results = await self._repo.search(
            query, limit=limit, audience=self._audience
        )
        logger.debug("关键词检索 '%s' → %d 条", query[:30], len(keyword_results))
        merged = self._merge_entries(keyword_results, entries, limit)
        results = await self._inject_featured(merged, limit)
        final_results = await self._prepend_live_data(results)
        await self._record_retrieval_log(
            query, RETRIEVAL_MODE_VECTOR_KEYWORD, final_results
        )
        return final_results

    async def _search_hybrid(self, query: str, limit: int) -> list[KnowledgeEntry]:
        candidate_limit = max(limit * 3, limit)
        vector_results: list[tuple[str, float]] = []
        bm25_results: list[tuple[str, float]] = []

        if self._vs and self._vs.doc_count > 0:
            vector_results = await asyncio.to_thread(
                self._vs.search, query, candidate_limit
            )
        if self._bm25 and self._bm25.doc_count > 0:
            bm25_results = await asyncio.to_thread(
                self._bm25.search, query, candidate_limit
            )

        fused_keys = fuse_ranked_results(
            [vector_results, bm25_results],
            limit=limit,
            rrf_k=self._rrf_k or DEFAULT_RRF_K,
        )
        if not fused_keys:
            return []

        entries = await self._repo.get_by_youzan_item_ids(
            fused_keys, limit=len(fused_keys), audience=self._audience
        )
        entries_by_key = {self._entry_key(entry): entry for entry in entries}
        ordered_entries = [
            entries_by_key[key] for key in fused_keys if key in entries_by_key
        ]
        logger.debug(
            "混合检索 '%s' → vector=%d bm25=%d fused=%d",
            query[:30],
            len(vector_results),
            len(bm25_results),
            len(ordered_entries),
        )
        return ordered_entries

    async def search_keyword_only(
        self, query: str, limit: int = 8
    ) -> list[KnowledgeEntry]:
        if not query.strip():
            return []
        results = await self._repo.search(query, limit=limit, audience=self._audience)
        logger.debug("精确关键词检索 '%s' → %d 条", query[:30], len(results))
        featured_results = await self._inject_featured(results, limit)
        final_results = await self._prepend_live_data(featured_results)
        await self._record_retrieval_log(
            query, RETRIEVAL_MODE_KEYWORD_ONLY, final_results
        )
        return final_results

    async def _record_retrieval_log(
        self,
        query: str,
        retrieval_mode: str,
        entries: list[KnowledgeEntry],
    ) -> None:
        await record_knowledge_retrieval_log(
            self._repo,
            bot_type=self._bot_type,
            audience=self._audience,
            query=query,
            retrieval_mode=retrieval_mode,
            entries=entries,
        )

    async def _prepend_live_data(
        self, entries: list[KnowledgeEntry]
    ) -> list[KnowledgeEntry]:
        return await prepend_live_data(
            self._repo,
            entries,
            product_repo=self._youzan_product_repo,
        )

    def _merge_entries(
        self,
        preferred_entries: list[KnowledgeEntry],
        fallback_entries: list[KnowledgeEntry],
        limit: int,
    ) -> list[KnowledgeEntry]:
        results: list[KnowledgeEntry] = []
        seen_titles: set[str] = set()
        for entry in [*preferred_entries, *fallback_entries]:
            if entry.title in seen_titles:
                continue
            results.append(entry)
            seen_titles.add(entry.title)
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def _entry_key(entry: KnowledgeEntry) -> str:
        return entry.youzan_item_id if entry.youzan_item_id else f"kb_{entry.id}"

    async def _inject_featured(
        self,
        results: list[KnowledgeEntry],
        limit: int,
    ) -> list[KnowledgeEntry]:
        """Prepend configured featured products only when they are sellable."""
        if not self._config_repo:
            return results
        products = await self._config_repo.get_list(FEATURED_PRODUCTS_KEY)
        if not products:
            return results

        featured_entries = await self._repo.get_by_titles(
            products, limit=len(products), audience=self._audience
        )
        featured_by_title = {entry.title: entry for entry in featured_entries}
        matched_featured_entries = [
            featured_by_title[title] for title in products if title in featured_by_title
        ]
        ordered_featured = await filter_recommendable_featured_products(
            self._repo,
            matched_featured_entries,
            product_repo=self._youzan_product_repo,
        )
        missing_titles = [title for title in products if title not in featured_by_title]
        if missing_titles:
            logger.warning(
                "后台主推款未匹配到启用商品知识: %s",
                "、".join(missing_titles),
            )

        if not ordered_featured:
            return results

        seen_titles = {entry.title for entry in ordered_featured}
        deduped_results = [entry for entry in results if entry.title not in seen_titles]
        return [*ordered_featured, *deduped_results][:limit]
