"""向量索引的磁盘持久化（save/load）。"""

from __future__ import annotations

import json
import os

from pathlib import Path

from app.logger import setup_logger
from app.readiness import resolve_embedding_path
from app.service.embedding_vector_math import normalize_matrix

logger = setup_logger()


async def save_index(
    searcher,  # type: ignore[no-untyped-def]  # EmbeddingSearcher 实例
    path: str | Path,
) -> None:
    """将向量索引安全持久化到磁盘。"""
    if not searcher._dirty:  # type: ignore[union-attr]
        logger.debug("向量索引未发生变更，跳过磁盘写入")
        return

    async with searcher._lock:  # type: ignore[union-attr]
        try:
            path = resolve_embedding_path(path)
            npy_path = path.with_suffix(".npy")
            json_path = path.with_suffix(".json")
            npy_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_npy = npy_path.with_suffix(".tmp.npy")
            tmp_json = json_path.with_suffix(".json.tmp")

            import numpy as np

            if searcher._embeddings is not None:  # type: ignore[union-attr]
                np.save(tmp_npy, searcher._embeddings)  # type: ignore[union-attr]
            else:
                np.save(tmp_npy, np.array([], dtype=np.float32))

            meta = {
                "doc_keys": searcher._doc_keys,  # type: ignore[union-attr]
                "ready": searcher._ready,  # type: ignore[union-attr]
                "data_hash": searcher._data_hash,  # type: ignore[union-attr]
            }
            with open(tmp_json, "w", encoding="utf-8") as file_obj:
                json.dump(meta, file_obj, ensure_ascii=False, indent=2)

            if tmp_npy.exists():
                os.replace(str(tmp_npy), str(npy_path))
            if tmp_json.exists():
                os.replace(str(tmp_json), str(json_path))

            searcher._dirty = False  # type: ignore[union-attr]
            logger.info("已安全持久化向量索引: %d 条", len(searcher._doc_keys))  # type: ignore[union-attr]
        except Exception as exc:
            logger.error("向量索引保存失败: %s", exc)


async def load_index(
    searcher,  # type: ignore[no-untyped-def]  # EmbeddingSearcher 实例
    path: str | Path,
) -> None:
    """从磁盘加载缓存的向量索引。"""
    searcher._init_progress["status"] = "loading"  # type: ignore[union-attr]
    async with searcher._lock:  # type: ignore[union-attr]
        try:
            path = resolve_embedding_path(path)
            npy_path = path.with_suffix(".npy")
            json_path = path.with_suffix(".json")

            if not npy_path.exists() or not json_path.exists():
                logger.warning("向量索引缓存文件不存在，将重新构建")
                searcher._ready = False  # type: ignore[union-attr]
                searcher._init_progress["status"] = "failed"  # type: ignore[union-attr]
                return

            with open(json_path, "r", encoding="utf-8") as file_obj:
                meta = json.load(file_obj)

            import numpy as np

            searcher._doc_keys = meta["doc_keys"]  # type: ignore[union-attr]
            searcher._ready = meta["ready"]  # type: ignore[union-attr]
            searcher._data_hash = meta.get("data_hash", "")  # type: ignore[union-attr]
            loaded_embeddings = np.load(npy_path)
            searcher._embeddings = normalize_matrix(  # type: ignore[union-attr]
                loaded_embeddings
            )
            if searcher._embeddings.size == 0:  # type: ignore[union-attr]
                searcher._embeddings = None  # type: ignore[union-attr]

            searcher._dirty = False  # type: ignore[union-attr]
            searcher._init_progress["status"] = "ready"  # type: ignore[union-attr]
            logger.info("Embedding 索引已从缓存加载: %d 条", len(searcher._doc_keys))  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("向量索引加载失败，将重新构建: %s", exc)
            searcher._ready = False  # type: ignore[union-attr]
            searcher._init_progress["status"] = "failed"  # type: ignore[union-attr]
