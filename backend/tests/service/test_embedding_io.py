from __future__ import annotations

import numpy as np

from app import readiness
from app.service.embedding_search import EmbeddingSearcher


async def test_embedding_save_and_load_resolve_relative_path_from_project_root(
    monkeypatch,
    tmp_path,
) -> None:
    project_root = tmp_path / "project"
    other_cwd = tmp_path / "other-cwd"
    project_root.mkdir()
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    monkeypatch.setattr(readiness, "ROOT_DIR", project_root)

    searcher = EmbeddingSearcher()
    searcher._embeddings = np.array([[1.0, 0.0]], dtype=np.float32)
    searcher._doc_keys = ["kb_1"]
    searcher._ready = True
    searcher._dirty = True
    searcher._data_hash = "hash"

    await searcher.save("data/embeddings")

    assert (project_root / "data" / "embeddings.npy").exists() is True
    assert (project_root / "data" / "embeddings.json").exists() is True
    assert (other_cwd / "data" / "embeddings.npy").exists() is False

    loaded = EmbeddingSearcher()
    await loaded.load("data/embeddings")

    assert loaded._ready is True
    assert loaded._doc_keys == ["kb_1"]
    assert loaded._data_hash == "hash"


async def test_embedding_load_marks_failed_when_cache_files_missing(tmp_path) -> None:
    searcher = EmbeddingSearcher()

    await searcher.load(tmp_path / "missing" / "embeddings")

    assert searcher._ready is False
    assert searcher._init_progress["status"] == "failed"


async def test_embedding_load_marks_failed_when_cache_metadata_is_invalid(
    tmp_path,
) -> None:
    index_path = tmp_path / "embeddings"
    index_path.with_suffix(".npy").write_bytes(b"not numpy")
    index_path.with_suffix(".json").write_text("{", encoding="utf-8")
    searcher = EmbeddingSearcher()

    await searcher.load(index_path)

    assert searcher._ready is False
    assert searcher._init_progress["status"] == "failed"
