from __future__ import annotations

DEFAULT_RRF_K = 60


def fuse_ranked_results(
    ranked_lists: list[list[tuple[str, float]]],
    *,
    limit: int,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[str]:
    """使用 RRF 融合多路检索排名，返回融合后的 key 顺序。"""
    if limit <= 0:
        return []

    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    seen_order = 0
    smooth_k = max(rrf_k, 1)

    for ranked in ranked_lists:
        seen_in_channel: set[str] = set()
        for rank, (key, _score) in enumerate(ranked, start=1):
            if key in seen_in_channel:
                continue
            seen_in_channel.add(key)
            if key not in first_seen:
                first_seen[key] = seen_order
                seen_order += 1
            scores[key] = scores.get(key, 0.0) + 1.0 / (smooth_k + rank)

    ordered_keys = sorted(
        scores,
        key=lambda item_key: (-scores[item_key], first_seen[item_key]),
    )
    return ordered_keys[:limit]
