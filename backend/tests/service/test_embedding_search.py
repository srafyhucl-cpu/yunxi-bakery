from __future__ import annotations

import json

import numpy as np

from app.service.embedding_search import EmbeddingSearcher


class _FixedQueryModel:
    def __init__(self, query_vector: list[float]) -> None:
        self._query_vector = np.array(query_vector, dtype=np.float32)

    def encode(
        self,
        texts: list[str],
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        del texts, normalize_embeddings, show_progress_bar
        return np.array([self._query_vector], dtype=np.float32)


def test_search_scores_use_normalized_dot_product() -> None:
    searcher = EmbeddingSearcher()
    searcher._model = _FixedQueryModel([3.0, 4.0])
    searcher._doc_keys = ["same", "orthogonal", "below-threshold"]
    searcher._embeddings = np.array(
        [
            [0.6, 0.8],
            [-0.8, 0.6],
            [0.2, 0.0],
        ],
        dtype=np.float32,
    )
    searcher._ready = True

    results = searcher.search("query", limit=3)

    assert [key for key, _ in results] == ["same"]
    assert np.isclose(results[0][1], 1.0)


async def test_upsert_one_normalizes_vectors_before_search() -> None:
    searcher = EmbeddingSearcher()
    searcher._model = _FixedQueryModel([10.0, 0.0])

    await searcher.upsert_one("doc", [3.0, 4.0])

    assert searcher._embeddings is not None
    assert np.isclose(np.linalg.norm(searcher._embeddings[0]), 1.0)
    results = searcher.search("query", limit=1)
    assert [key for key, _ in results] == ["doc"]
    assert np.isclose(results[0][1], 0.6)


async def test_load_normalizes_legacy_cache_vectors(tmp_path) -> None:
    index_path = tmp_path / "embeddings"
    np.save(index_path.with_suffix(".npy"), np.array([[3.0, 4.0]], dtype=np.float32))
    index_path.with_suffix(".json").write_text(
        json.dumps({"doc_keys": ["doc"], "ready": True, "data_hash": "hash"}),
        encoding="utf-8",
    )

    searcher = EmbeddingSearcher()
    await searcher.load(index_path)

    assert searcher._embeddings is not None
    assert np.isclose(np.linalg.norm(searcher._embeddings[0]), 1.0)
