"""
离线检索评测脚本 —— Recall@K / MRR。

用途：
    在金标准标注集（tests/fixtures/retrieval_eval_set.json）上评测知识检索质量，
    用于线 A（BM25 + RRF 混合检索）改造前后的客观对比。

数据来源：
    从 --db 指定的 SQLite 库读取 knowledge_base 作为检索语料（建议用
    scripts/pull_prod_snapshot.sh 白名单导出的生产快照 data/prod_snapshot/eval.db）。

检索模式（--mode）：
    vector  —— 仅向量（现状基线，默认）
    hybrid  —— 向量 + BM25 + RRF（线 A 改造后；A1 落地后可用）
    planned-vector —— query plan + 仅向量
    planned-hybrid —— query plan + 向量 + BM25 + RRF

命中判定：
    标注集中每条用例的 relevant 是一组『匹配器』，匹配器为关键词列表。
    某召回文档的 (title + content) 若包含某匹配器中的全部关键词，即视为命中。

用法：
    python scripts/eval_retrieval.py --db data/prod_snapshot/eval.db
    python scripts/eval_retrieval.py --db data/prod_snapshot/eval.db --mode vector --k 5
    python scripts/eval_retrieval.py --db data/prod_snapshot/eval.db --mode planned-vector --k 5
    python scripts/eval_retrieval.py --db data/prod_snapshot/eval.db --mode planned-hybrid --k 5
    python scripts/eval_retrieval.py --db data/prod_snapshot/eval.db --mode planned-hybrid --rerank --k 5
    python scripts/eval_retrieval.py --db data/prod_snapshot/eval.db --fixture tests/fixtures/customer_rag_golden_cases.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 评测使用与生产一致的本地编码器；若环境无模型权重，可设
# YUNXI_USE_FAKE_EMBEDDING=1 用轻量哈希编码器跑通流程（此时分数仅供管线验证）。
from app.service.embedding_search import EmbeddingSearcher  # noqa: E402
from app.service.bm25_search import BM25Searcher  # noqa: E402
from app.service.agents.rag.query import (  # noqa: E402
    RagQueryVariant,
    build_customer_rag_query_plan,
)
from app.service.agents.rag.rerank import rerank_documents_by_query_rules  # noqa: E402
from app.service.retrieval_fusion import DEFAULT_RRF_K, fuse_ranked_results  # noqa: E402

MODE_VECTOR = "vector"
MODE_HYBRID = "hybrid"
MODE_PLANNED_VECTOR = "planned-vector"
MODE_PLANNED_HYBRID = "planned-hybrid"
PLANNED_MODES = {MODE_PLANNED_VECTOR, MODE_PLANNED_HYBRID}
HYBRID_MODES = {MODE_HYBRID, MODE_PLANNED_HYBRID}
DEFAULT_RERANK_CANDIDATE_MULTIPLIER = 3

DEFAULT_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "fixtures"
    / "retrieval_eval_set.json"
)
DEFAULT_EVALUATION_DB = Path("data/prod_snapshot/eval.db")


def load_eval_set(fixture_path: str | Path = DEFAULT_FIXTURE_PATH) -> list[dict]:
    """加载金标准标注集，过滤占位项。"""
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [c for c in data["cases"] if "query" in c]


def resolve_db_path(db_arg: str) -> Path:
    """解析评测库路径：优先使用显式入参，否则只接受安全评测库。"""
    if db_arg:
        return Path(db_arg)
    return DEFAULT_EVALUATION_DB


def load_corpus(db_path: str | Path) -> list[tuple[str, str, str]]:
    """从知识库读取检索语料：返回 (key, title, content) 列表。

    key 形态与 KnowledgeRepo.get_all_titles_with_keys 对齐：
    有 youzan_item_id 用之，否则用 kb_{id}。
    """
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, youzan_item_id, title, content "
            "FROM knowledge_base WHERE is_active = 1"
        ).fetchall()
    corpus: list[tuple[str, str, str]] = []
    for r in rows:
        key = str(r["youzan_item_id"]) if r["youzan_item_id"] else f"kb_{r['id']}"
        corpus.append((key, r["title"] or "", r["content"] or ""))
    return corpus


def doc_matches_case(title: str, content: str, relevant: list[list[str]]) -> bool:
    """判断单个文档是否命中用例目标：含任一匹配器中的全部关键词即命中。"""
    haystack = f"{title} {content}"
    for matcher in relevant:
        if all(kw in haystack for kw in matcher):
            return True
    return False


def build_key_relevance(
    corpus: list[tuple[str, str, str]], relevant: list[list[str]]
) -> set[str]:
    """根据匹配器，算出语料中哪些 key 是该用例的相关文档。"""
    return {
        key
        for key, title, content in corpus
        if doc_matches_case(title, content, relevant)
    }


class HybridEvalSearcher:
    """评测脚本专用的向量 + BM25 + RRF 包装器。"""

    def __init__(
        self,
        vector_searcher: EmbeddingSearcher,
        bm25_searcher: BM25Searcher,
    ) -> None:
        self._vector_searcher = vector_searcher
        self._bm25_searcher = bm25_searcher

    def search(self, query: str, limit: int = 8) -> list[tuple[str, float]]:
        candidate_limit = max(limit * 3, limit)
        vector_results = self._vector_searcher.search(query, limit=candidate_limit)
        bm25_results = self._bm25_searcher.search(query, limit=candidate_limit)
        fused_keys = fuse_ranked_results(
            [vector_results, bm25_results],
            limit=limit,
            rrf_k=DEFAULT_RRF_K,
        )
        return [(key, float(limit - index)) for index, key in enumerate(fused_keys)]


class PlannedQueryEvalSearcher:
    """评测脚本专用的 query plan 多查询包装器。"""

    def __init__(self, base_searcher: object) -> None:
        self._base_searcher = base_searcher

    def search(self, query: str, limit: int = 8) -> list[tuple[str, float]]:
        plan = build_customer_rag_query_plan(query)
        variants = plan.variants or (RagQueryVariant(query=query, reason="original"),)
        seen_keys: set[str] = set()
        ranked_results: list[tuple[str, float]] = []
        for variant in variants:
            results = self._base_searcher.search(variant.query, limit=limit)
            for key, score in results:
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                ranked_results.append((key, float(score)))
                if len(ranked_results) >= limit:
                    return ranked_results
        return ranked_results


class RerankEvalSearcher:
    """评测脚本专用的 Document rerank 包装器。"""

    def __init__(
        self,
        base_searcher: object,
        corpus: list[tuple[str, str, str]],
        candidate_multiplier: int = DEFAULT_RERANK_CANDIDATE_MULTIPLIER,
    ) -> None:
        self._base_searcher = base_searcher
        self._documents_by_key = _build_eval_documents_by_key(corpus)
        self._candidate_multiplier = max(candidate_multiplier, 1)

    def search(self, query: str, limit: int = 8) -> list[tuple[str, float]]:
        candidate_limit = max(limit * self._candidate_multiplier, limit)
        results = self._base_searcher.search(query, limit=candidate_limit)
        documents = [
            self._documents_by_key[key]
            for key, _score in results
            if key in self._documents_by_key
        ]
        reranked_documents = rerank_documents_by_query_rules(query, documents)
        return [
            (document.metadata["key"], float(limit - index))
            for index, document in enumerate(reranked_documents[:limit])
        ]


def _build_eval_documents_by_key(
    corpus: list[tuple[str, str, str]],
) -> dict[str, SimpleNamespace]:
    return {
        key: SimpleNamespace(
            page_content=content,
            metadata={"key": key, "title": title, "category": ""},
        )
        for key, title, content in corpus
    }


def evaluate(
    cases: list[dict],
    corpus: list[tuple[str, str, str]],
    searcher: object,
    k: int,
) -> dict:
    """跑评测，返回汇总指标与逐例明细。"""
    title_by_key = {key: title for key, title, _ in corpus}
    recall_hits = 0
    mrr_sum = 0.0
    no_gold = 0  # 标注集里有、但当前语料无对应文档的用例（无法评测）
    details: list[dict] = []
    group_counters: dict[str, dict[str, float | int]] = {}

    for case in cases:
        group = str(case.get("group", "ungrouped") or "ungrouped")
        gold_keys = build_key_relevance(corpus, case["relevant"])
        if not gold_keys:
            no_gold += 1
            _count_no_gold(group_counters, group)
            details.append(
                {
                    "id": case["id"],
                    "group": group,
                    "query": case["query"],
                    "status": "NO_GOLD",
                    "note": "当前语料中无匹配的目标文档，跳过",
                }
            )
            continue

        results = searcher.search(case["query"], limit=k)
        ranked_keys = [key for key, _ in results]

        # Recall@K：top-K 中是否至少命中一个相关文档
        hit = any(key in gold_keys for key in ranked_keys)
        recall_hits += 1 if hit else 0

        # MRR：第一个相关文档的倒数排名
        rr = 0.0
        first_rank = None
        for rank, key in enumerate(ranked_keys, start=1):
            if key in gold_keys:
                rr = 1.0 / rank
                first_rank = rank
                break
        mrr_sum += rr
        _count_evaluable_case(group_counters, group, hit=hit, rr=rr)

        details.append(
            {
                "id": case["id"],
                "group": group,
                "query": case["query"],
                "status": "HIT" if hit else "MISS",
                "first_rank": first_rank,
                "top_titles": [title_by_key.get(key, key) for key in ranked_keys[:3]],
            }
        )

    evaluable = len(cases) - no_gold
    return {
        "k": k,
        "total_cases": len(cases),
        "evaluable": evaluable,
        "no_gold": no_gold,
        "recall_at_k": round(recall_hits / evaluable, 4) if evaluable else 0.0,
        "mrr": round(mrr_sum / evaluable, 4) if evaluable else 0.0,
        "group_metrics": _build_group_metrics(group_counters),
        "details": details,
    }


def _count_no_gold(counters: dict[str, dict[str, float | int]], group: str) -> None:
    counter = _group_counter(counters, group)
    counter["total_cases"] += 1
    counter["no_gold"] += 1


def _count_evaluable_case(
    counters: dict[str, dict[str, float | int]],
    group: str,
    *,
    hit: bool,
    rr: float,
) -> None:
    counter = _group_counter(counters, group)
    counter["total_cases"] += 1
    counter["evaluable"] += 1
    counter["hits"] += 1 if hit else 0
    counter["mrr_sum"] += rr


def _group_counter(
    counters: dict[str, dict[str, float | int]], group: str
) -> dict[str, float | int]:
    if group not in counters:
        counters[group] = {
            "total_cases": 0,
            "evaluable": 0,
            "no_gold": 0,
            "hits": 0,
            "mrr_sum": 0.0,
        }
    return counters[group]


def _build_group_metrics(
    counters: dict[str, dict[str, float | int]],
) -> dict[str, dict[str, float | int]]:
    metrics: dict[str, dict[str, float | int]] = {}
    for group, counter in sorted(counters.items()):
        evaluable = int(counter["evaluable"])
        metrics[group] = {
            "total_cases": int(counter["total_cases"]),
            "evaluable": evaluable,
            "no_gold": int(counter["no_gold"]),
            "recall_at_k": round(int(counter["hits"]) / evaluable, 4)
            if evaluable
            else 0.0,
            "mrr": round(float(counter["mrr_sum"]) / evaluable, 4)
            if evaluable
            else 0.0,
        }
    return metrics


def print_report(mode: str, db_path: str, corpus_size: int, summary: dict) -> None:
    """打印评测报告。"""
    print("=" * 60)
    print(f"  检索评测报告 — mode={mode}")
    print("=" * 60)
    print(f"  语料库:        {db_path}（{corpus_size} 条启用知识）")
    print(f"  用例总数:      {summary['total_cases']}")
    print(
        f"  可评测用例:    {summary['evaluable']}（NO_GOLD 跳过 {summary['no_gold']}）"
    )
    print(f"  Recall@{summary['k']}:     {summary['recall_at_k']}")
    print(f"  MRR:           {summary['mrr']}")
    if summary.get("rerank"):
        print(
            "  Rerank:        enabled "
            f"(candidate_multiplier={summary['rerank_candidate_multiplier']})"
        )
    if summary.get("group_metrics"):
        print("  分组指标:")
        for group, metrics in summary["group_metrics"].items():
            print(
                f"    {group}: Recall={metrics['recall_at_k']} "
                f"MRR={metrics['mrr']} "
                f"evaluable={metrics['evaluable']} "
                f"NO_GOLD={metrics['no_gold']}"
            )
    print("-" * 60)
    miss = [d for d in summary["details"] if d["status"] == "MISS"]
    if miss:
        print(f"  未命中用例（{len(miss)}）:")
        for d in miss:
            print(f"    [{d['id']}] {d['query']}  → top3: {d.get('top_titles')}")
    no_gold = [d for d in summary["details"] if d["status"] == "NO_GOLD"]
    if no_gold:
        print(f"  无目标文档用例（{len(no_gold)}，语料未覆盖）:")
        for d in no_gold:
            print(f"    [{d['id']}] {d['query']}")
    print("=" * 60)


async def main() -> int:
    parser = argparse.ArgumentParser(description="离线检索评测 Recall@K / MRR")
    parser.add_argument(
        "--db",
        default="",
        help=(
            "检索语料 SQLite 库；未指定时优先使用 data/prod_snapshot/eval.db，"
            "请先运行白名单快照导出，不允许使用原始生产快照"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=[
            MODE_VECTOR,
            MODE_HYBRID,
            MODE_PLANNED_VECTOR,
            MODE_PLANNED_HYBRID,
        ],
        default=MODE_VECTOR,
        help=(
            "检索模式：vector=纯向量基线（默认）；hybrid=向量+BM25+RRF；"
            "planned-vector/planned-hybrid=先做 query plan 再检索"
        ),
    )
    parser.add_argument("--k", type=int, default=5, help="Recall@K 与召回截断的 K")
    parser.add_argument(
        "--rerank",
        action="store_true",
        help="显式启用规则 rerank；会扩大候选池后再按规则排序，不作为默认基线",
    )
    parser.add_argument(
        "--rerank-candidate-multiplier",
        type=int,
        default=DEFAULT_RERANK_CANDIDATE_MULTIPLIER,
        help="启用 --rerank 时的候选池倍数，默认 3",
    )
    parser.add_argument(
        "--json-out", default="", help="可选：将汇总指标写入该 JSON 路径"
    )
    parser.add_argument(
        "--fixture",
        default=str(DEFAULT_FIXTURE_PATH),
        help="评测标注集路径，默认 tests/fixtures/retrieval_eval_set.json",
    )
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)
    if not db_path.exists():
        print(f"[ERROR] 语料库不存在: {db_path}", file=sys.stderr)
        print("        请先运行: bash scripts/pull_prod_snapshot.sh", file=sys.stderr)
        return 1

    corpus = load_corpus(db_path)
    if not corpus:
        print(f"[ERROR] {db_path} 中无启用知识，无法评测", file=sys.stderr)
        return 1

    cases = load_eval_set(args.fixture)

    # 构建向量索引（与生产同源：title + content）
    searcher = EmbeddingSearcher()
    searcher.build(corpus)
    if args.mode in HYBRID_MODES:
        bm25_searcher = BM25Searcher()
        bm25_searcher.build(corpus)
        searcher = HybridEvalSearcher(searcher, bm25_searcher)
    if args.mode in PLANNED_MODES:
        searcher = PlannedQueryEvalSearcher(searcher)
    if args.rerank:
        searcher = RerankEvalSearcher(
            searcher,
            corpus,
            candidate_multiplier=args.rerank_candidate_multiplier,
        )

    summary = evaluate(cases, corpus, searcher, k=args.k)
    summary["rerank"] = bool(args.rerank)
    if args.rerank:
        summary["rerank_candidate_multiplier"] = max(
            args.rerank_candidate_multiplier,
            1,
        )
    print_report(args.mode, str(db_path), len(corpus), summary)

    if args.json_out:
        slim = {key: val for key, val in summary.items() if key != "details"}
        slim["mode"] = args.mode
        slim["fixture"] = args.fixture
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(slim, f, ensure_ascii=False, indent=2)
        print(f"[INFO] 汇总指标已写入 {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
