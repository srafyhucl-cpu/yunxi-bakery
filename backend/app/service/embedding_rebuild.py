"""向量索引从数据库重建的工具函数。"""

from __future__ import annotations

import asyncio
import hashlib

from app.logger import setup_logger
from app.service.embedding_search import EmbeddingSearcher

logger = setup_logger()


async def rebuild_from_db(searcher: EmbeddingSearcher, index_dir: str = "") -> None:
    """从数据库读取全部条目，并在后台线程全量重构向量索引并落盘。"""
    searcher._init_progress["status"] = "loading"  # type: ignore[union-attr]
    try:
        from app.database import db_session_scope
        from app.repository.knowledge_repo import KnowledgeRepo

        async with db_session_scope():
            repo = KnowledgeRepo(None)
            docs = await repo.get_all_titles_with_keys()

            sorted_docs = sorted(docs, key=lambda x: x[0])
            concat_text = "".join(f"{d[1]}{d[2]}" for d in sorted_docs)
            current_db_md5 = hashlib.md5(concat_text.encode("utf-8")).hexdigest()

            logger.info("后台自愈：开始从数据库全量重构向量索引...")
            await asyncio.to_thread(searcher.build, docs, current_db_md5)

            if index_dir:
                await searcher.save(index_dir)
            logger.info("后台自愈：向量索引自愈重构并落盘完成")
    except Exception as exc:
        searcher._init_progress["status"] = "failed"  # type: ignore[union-attr]
        logger.error("后台自愈：异步向量自愈重构遭遇严重异常: %s", exc)
