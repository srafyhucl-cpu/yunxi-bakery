"""lifespan 阶段向量搜索初始化逻辑（从 main.py 拆出，降低入口文件体量）。"""

import asyncio
from typing import Any

from app.logger import setup_logger
from app.repository.knowledge_repo import KnowledgeRepo

logger = setup_logger()


async def init_vector_search(
    app: Any, knowledge_repo: KnowledgeRepo
) -> tuple[Any, Any, asyncio.Task[None]]:
    """初始化语义向量搜索服务，返回向量搜索实例和定时刷盘任务。"""
    from app.service.embedding_search import EmbeddingSearcher

    if hasattr(app.state, "settings"):
        settings_obj = app.state.settings
    else:
        from app.config import settings

        settings_obj = settings

    vs = EmbeddingSearcher()
    vs_path = settings_obj.EMBEDDING_INDEX_DIR
    app.state.vs = vs
    bm25 = None
    if settings_obj.ENABLE_HYBRID_RETRIEVAL:
        from app.service.bm25_search import BM25Searcher

        bm25 = BM25Searcher()
        app.state.bm25 = bm25

    # 异步初始化向量索引（优先加载缓存，必要时重建）
    async def async_init_vector_search() -> None:
        try:
            vs._init_progress["status"] = "loading"
            from app.database import db_session_scope

            async with db_session_scope():
                logger.info("正在异步初始化向量搜索：首选尝试极速载入本地预解算缓存...")
                await vs.load(vs_path)

                docs = await knowledge_repo.get_all_titles_with_keys()
                if bm25 is not None:
                    await asyncio.to_thread(bm25.build, docs)
                need_rebuild = True

                import hashlib

                sorted_docs = sorted(docs, key=lambda x: x[0])
                concat_text = "".join(f"{d[1]}{d[2]}" for d in sorted_docs)
                current_db_md5 = hashlib.md5(concat_text.encode("utf-8")).hexdigest()

                if vs._ready and docs:
                    cached_keys = set(vs._doc_keys)
                    db_keys = {str(d[0]) for d in docs}
                    if cached_keys == db_keys and vs._data_hash == current_db_md5:
                        need_rebuild = False
                        vs._init_progress["status"] = "ready"
                        logger.info(
                            "向量缓存指纹与文本特征 MD5 已完全对齐，直接载入启动，共有 %d 条向量",
                            vs.doc_count,
                        )

                if need_rebuild:
                    if docs:
                        logger.info(
                            "向量缓存缺失或数据指纹不对齐（数据发生漂移），正在后台启动全量向量构建..."
                        )
                        await asyncio.to_thread(vs.build, docs, current_db_md5)
                        await vs.save(vs_path)
                        logger.info(
                            "全量向量自愈构建并落盘完成，对齐并持久化 %d 条活跃向量",
                            vs.doc_count,
                        )
                    else:
                        vs._init_progress["status"] = "ready"
                        logger.warning("知识库中尚无活跃条目，跳过启动向量构建")
        except Exception as exc:
            vs._init_progress["status"] = "failed"
            logger.error("异步初始化向量搜索遭遇严重异常: %s", exc)

    init_task = asyncio.create_task(async_init_vector_search())
    app.state.bg_tasks = (
        app.state.bg_tasks | {init_task}
        if hasattr(app.state, "bg_tasks")
        else {init_task}
    )
    init_task.add_done_callback(lambda t: app.state.bg_tasks.discard(t))

    # 异步定时节流刷盘后台守护任务
    async def periodic_save_task() -> None:
        try:
            while True:
                try:
                    await asyncio.wait_for(vs._save_event.wait(), timeout=120.0)
                    vs._save_event.clear()
                except asyncio.TimeoutError:
                    pass
                if vs and vs._dirty:
                    from app.database import db_session_scope

                    async with db_session_scope():
                        active_docs = await knowledge_repo.get_all_titles_with_keys()
                        import hashlib

                        sorted_active_docs = sorted(active_docs, key=lambda x: x[0])
                        concat_str = "".join(
                            f"{d[1]}{d[2]}" for d in sorted_active_docs
                        )
                        latest_db_md5 = hashlib.md5(
                            concat_str.encode("utf-8")
                        ).hexdigest()
                        vs._data_hash = latest_db_md5
                        await vs.save(vs_path)
        except asyncio.CancelledError:
            # 正常退出拦截器，最后一次强制清算持久化
            if vs and vs._dirty:
                try:
                    from app.database import db_session_scope

                    async with db_session_scope():
                        active_docs = await knowledge_repo.get_all_titles_with_keys()
                        import hashlib

                        sorted_active_docs = sorted(active_docs, key=lambda x: x[0])
                        concat_str = "".join(
                            f"{d[1]}{d[2]}" for d in sorted_active_docs
                        )
                        latest_db_md5 = hashlib.md5(
                            concat_str.encode("utf-8")
                        ).hexdigest()
                        vs._data_hash = latest_db_md5
                        await vs.save(vs_path)
                except Exception as e:
                    logger.error("守护协程退关刷盘异常: %s", e)
        except Exception as e:
            logger.error("定时节流刷盘守护协程异常: %s", e)

    save_task = asyncio.create_task(periodic_save_task())
    return vs, bm25, save_task
