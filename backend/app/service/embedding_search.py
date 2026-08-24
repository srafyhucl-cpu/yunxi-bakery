"""基于 Sentence-Transformers 的语义向量搜索引擎。"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from app.logger import setup_logger
from app.readiness import resolve_embedding_path
from app.service.embedding_model import (
    BGE_QUERY_PREFIX,
    EMBEDDING_MODEL,
    MIN_SIMILARITY_SCORE,
    _FallbackSentenceTransformer,
)
from app.service.embedding_vector_math import (
    normalize_matrix,
    normalize_vector,
    top_k_indices,
)

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = setup_logger()
EMBEDDING_BATCH_SIZE = 16


class EmbeddingSearcher:
    """Sentence-Transformers 语义向量搜索实现。"""

    def __init__(self) -> None:
        self._model: SentenceTransformer | _FallbackSentenceTransformer | None = None
        self._embeddings: np.ndarray | None = None
        self._doc_keys: list[str] = []
        self._ready = False
        self._dirty = False
        self._data_hash = ""
        self._lock = asyncio.Lock()
        self._save_event = asyncio.Event()
        self._init_progress = {
            "status": "uninitialized",
            "total": 0,
            "current": 0,
            "start_time": 0.0,
            "elapsed": 0.0,
            "last_build_duration": 0.0,
        }
        try:
            duration_file = resolve_embedding_path("data/vector_last_duration.json")
            if duration_file.exists():
                with open(duration_file, "r", encoding="utf-8") as f:
                    self._init_progress["last_build_duration"] = json.load(f).get(
                        "last_build_duration", 0.0
                    )
        except Exception:
            pass

    def _get_model(self) -> SentenceTransformer | _FallbackSentenceTransformer:
        """惰性初始化模型，避免模块导入阶段触发重型依赖加载。"""
        if self._model is None:
            if os.getenv("YUNXI_USE_FAKE_EMBEDDING", "0") == "1":
                self._model = _FallbackSentenceTransformer()
                logger.warning("Embedding 检索已切换到测试轻量编码器")
                return self._model

            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            # 关闭 transformers 的异步权重物化，规避 Windows + Python 3.13 下的偶发崩溃。
            os.environ.setdefault("HF_DEACTIVATE_ASYNC_LOAD", "1")

            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
            logger.info("Embedding 模型已加载: %s", EMBEDDING_MODEL)
        return self._model

    def build(
        self, documents: list[tuple[str, str, str]], current_db_md5: str = ""
    ) -> None:
        """全量构建语义向量索引并分批更新进度。"""
        import time

        model = self._get_model()
        self._doc_keys = [str(doc_key) for doc_key, _title, _content in documents]
        texts = [f"{title} {content}" for _doc_key, title, content in documents]
        total_docs = len(texts)
        self._init_progress.update(
            {"status": "building", "total": total_docs, "current": 0},
        )
        self._init_progress["start_time"] = time.time()
        self._init_progress["elapsed"] = 0.0

        all_embeddings: list[np.ndarray] = []
        for i in range(0, total_docs, EMBEDDING_BATCH_SIZE):
            batch_texts = texts[i : i + EMBEDDING_BATCH_SIZE]
            batch_raw = model.encode(
                batch_texts, normalize_embeddings=True, show_progress_bar=False
            )
            all_embeddings.append(batch_raw)
            self._init_progress["current"] = min(i + EMBEDDING_BATCH_SIZE, total_docs)
            self._init_progress["elapsed"] = (
                time.time() - self._init_progress["start_time"]
            )

        embeddings = np.vstack(all_embeddings) if all_embeddings else np.zeros((0, 256))
        self._embeddings = normalize_matrix(embeddings)
        self._ready = True
        self._dirty = True
        self._data_hash = current_db_md5
        self._init_progress["status"] = "ready"

        duration = time.time() - self._init_progress["start_time"]
        self._init_progress["last_build_duration"] = duration
        try:
            duration_file = resolve_embedding_path("data/vector_last_duration.json")
            duration_file.parent.mkdir(parents=True, exist_ok=True)
            with open(duration_file, "w", encoding="utf-8") as f:
                json.dump({"last_build_duration": duration}, f)
        except Exception:
            pass
        logger.info(
            "Embedding 索引构建完成: %d 条，耗时 %.2f 秒", len(self._doc_keys), duration
        )

    def search(self, query: str, limit: int = 8) -> list[tuple[str, float]]:
        """按归一化向量点积检索文档，分数语义等价 cosine similarity。"""
        if not self._ready or self._embeddings is None or limit <= 0:
            return []

        model = self._get_model()
        prefixed = BGE_QUERY_PREFIX + query
        q_vec = model.encode([prefixed], normalize_embeddings=True)
        q_vec = normalize_vector(q_vec[0])
        scores: np.ndarray = self._embeddings @ q_vec
        return [
            (self._doc_keys[i], float(scores[i]))
            for i in top_k_indices(scores, limit)
            if scores[i] > MIN_SIMILARITY_SCORE
        ]

    async def upsert_one(self, key: str, vector: list[float]) -> None:
        """单条追加或原位替换向量。"""
        async with self._lock:
            new_vec = normalize_vector(np.array(vector, dtype=np.float32))
            if key in self._doc_keys:
                index = self._doc_keys.index(key)
                if self._embeddings is not None:
                    self._embeddings[index] = new_vec
                logger.info("已通过内存原子替换增量更新单条向量: %s", key)
            else:
                self._doc_keys.append(key)
                if (
                    self._embeddings is None
                    or self._embeddings.size == 0
                    or len(self._embeddings.shape) < 2
                ):
                    self._embeddings = np.array([new_vec], dtype=np.float32)
                else:
                    self._embeddings = np.vstack([self._embeddings, new_vec])
                logger.info("已通过内存增量追加单条向量: %s", key)
            self._ready = True
            self._dirty = True
            self._save_event.set()

    async def delete_one(self, key: str) -> None:
        """单条物理删除向量。"""
        async with self._lock:
            if key in self._doc_keys:
                index = self._doc_keys.index(key)
                self._doc_keys.pop(index)
                if self._embeddings is not None:
                    self._embeddings = np.delete(self._embeddings, index, axis=0)
                logger.info("已从内存原子删除单条向量: %s", key)
                self._dirty = True
                self._save_event.set()
                if not self._doc_keys:
                    self._ready = False
                    self._embeddings = None

    async def save(self, path: str | Path) -> None:
        """将向量索引安全持久化到磁盘。"""
        from app.service.embedding_io import save_index

        await save_index(self, path)

    async def load(self, path: str | Path) -> None:
        """从磁盘加载缓存的向量索引。"""
        from app.service.embedding_io import load_index

        await load_index(self, path)

    @property
    def doc_count(self) -> int:
        return len(self._doc_keys)

    async def rebuild_from_db(self, index_dir: str | Path = "") -> None:
        """从数据库读取全部条目，并在后台线程全量重构向量索引并落盘。"""
        from app.service.embedding_rebuild import rebuild_from_db

        await rebuild_from_db(self, str(index_dir))
