"""Embedding 向量数学工具。"""

from __future__ import annotations

import numpy as np


def normalize_vector(vector: np.ndarray) -> np.ndarray:
    """返回 float32 L2 归一化向量，零向量保持不变。"""
    normalized = vector.astype(np.float32, copy=False)
    norm = np.linalg.norm(normalized)
    if norm > 0:
        normalized = normalized / norm
    return normalized.astype(np.float32, copy=False)


def normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    """返回逐行 L2 归一化矩阵，兼容旧缓存中的未归一化向量。"""
    normalized = matrix.astype(np.float32, copy=False)
    if normalized.size == 0:
        return normalized
    if normalized.ndim == 1:
        normalized = normalized.reshape(1, -1)
    norms = np.linalg.norm(normalized, axis=1, keepdims=True)
    safe_norms = np.where(norms > 0, norms, 1.0)
    return (normalized / safe_norms).astype(np.float32, copy=False)


def top_k_indices(scores: np.ndarray, limit: int) -> np.ndarray:
    """返回按分数降序排列的 Top-K 下标。"""
    if len(scores) > limit:
        candidates = np.argpartition(scores, -limit)[-limit:]
        return candidates[np.argsort(scores[candidates])[::-1]]
    return np.argsort(scores)[::-1]
