"""Embedding 模型定义与轻量回退编码器。"""

from __future__ import annotations

import numpy as np

from app.logger import setup_logger

logger = setup_logger()

EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："
MIN_SIMILARITY_SCORE = 0.35


class _FallbackSentenceTransformer:
    """测试环境使用的轻量编码器，避免特定解释器下真实模型加载崩溃。"""

    def encode(
        self,
        texts: list[str],
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        del show_progress_bar
        rows: list[np.ndarray] = []
        for text in texts:
            vector = np.zeros(256, dtype=np.float32)
            for index, char in enumerate(text):
                bucket = (ord(char) + index * 131) % 256
                vector[bucket] += 1.0
            if normalize_embeddings:
                norm = np.linalg.norm(vector)
                if norm > 0:
                    vector = vector / norm
            rows.append(vector)
        if not rows:
            return np.zeros((0, 256), dtype=np.float32)
        return np.vstack(rows)
