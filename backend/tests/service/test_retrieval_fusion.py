from app.service.retrieval_fusion import fuse_ranked_results


def test_fuse_ranked_results_boosts_docs_seen_by_multiple_channels() -> None:
    fused = fuse_ranked_results(
        [
            [("vector-only", 0.95), ("shared", 0.9)],
            [("shared", 12.0), ("bm25-only", 8.0)],
        ],
        limit=3,
        rrf_k=60,
    )

    assert fused == ["shared", "vector-only", "bm25-only"]


def test_fuse_ranked_results_deduplicates_channel_results() -> None:
    fused = fuse_ranked_results(
        [[("same", 1.0), ("same", 0.9), ("other", 0.8)]],
        limit=5,
        rrf_k=60,
    )

    assert fused == ["same", "other"]


def test_fuse_ranked_results_returns_empty_for_invalid_limit() -> None:
    assert fuse_ranked_results([[("doc", 1.0)]], limit=0) == []
