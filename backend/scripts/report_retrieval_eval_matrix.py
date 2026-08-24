"""离线检索评测矩阵报告。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts import eval_retrieval  # noqa: E402


@dataclass(frozen=True)
class EvalScenario:
    mode: str
    rerank: bool = False

    @property
    def name(self) -> str:
        if self.rerank:
            return f"{self.mode}+rerank"
        return self.mode


DEFAULT_SCENARIOS = (
    EvalScenario(eval_retrieval.MODE_VECTOR),
    EvalScenario(eval_retrieval.MODE_HYBRID),
    EvalScenario(eval_retrieval.MODE_PLANNED_HYBRID),
    EvalScenario(eval_retrieval.MODE_PLANNED_HYBRID, rerank=True),
)


@dataclass(frozen=True)
class EvalSearchIndexes:
    vector_searcher: Any
    bm25_searcher: Any | None


def build_search_indexes(
    scenarios: tuple[EvalScenario, ...],
    corpus: list[tuple[str, str, str]],
) -> EvalSearchIndexes:
    vector_searcher = eval_retrieval.EmbeddingSearcher()
    vector_searcher.build(corpus)
    bm25_searcher = None
    if any(scenario.mode in eval_retrieval.HYBRID_MODES for scenario in scenarios):
        bm25_searcher = eval_retrieval.BM25Searcher()
        bm25_searcher.build(corpus)
    return EvalSearchIndexes(
        vector_searcher=vector_searcher,
        bm25_searcher=bm25_searcher,
    )


def build_searcher(
    scenario: EvalScenario,
    indexes: EvalSearchIndexes,
    corpus: list[tuple[str, str, str]],
    *,
    rerank_candidate_multiplier: int,
) -> Any:
    searcher: Any = indexes.vector_searcher
    if scenario.mode in eval_retrieval.HYBRID_MODES:
        if indexes.bm25_searcher is None:
            raise ValueError("hybrid 场景缺少 BM25 索引")
        searcher = eval_retrieval.HybridEvalSearcher(searcher, indexes.bm25_searcher)
    if scenario.mode in eval_retrieval.PLANNED_MODES:
        searcher = eval_retrieval.PlannedQueryEvalSearcher(searcher)
    if scenario.rerank:
        searcher = eval_retrieval.RerankEvalSearcher(
            searcher,
            corpus,
            candidate_multiplier=rerank_candidate_multiplier,
        )
    return searcher


def run_matrix(
    *,
    db_path: Path,
    fixture_path: Path,
    k: int,
    rerank_candidate_multiplier: int,
    scenarios: tuple[EvalScenario, ...] = DEFAULT_SCENARIOS,
) -> dict[str, Any]:
    corpus = eval_retrieval.load_corpus(db_path)
    if not corpus:
        raise ValueError(f"{db_path} 中无启用知识，无法评测")

    cases = eval_retrieval.load_eval_set(fixture_path)
    indexes = build_search_indexes(scenarios, corpus)
    results = [
        _run_scenario(
            scenario,
            indexes,
            corpus,
            cases,
            db_path=db_path,
            fixture_path=fixture_path,
            k=k,
            rerank_candidate_multiplier=rerank_candidate_multiplier,
        )
        for scenario in scenarios
    ]
    return {
        "metadata": {
            "db": str(db_path),
            "fixture": str(fixture_path),
            "k": k,
            "corpus_size": len(corpus),
            "total_cases": len(cases),
        },
        "best": _select_best_result(results),
        "results": results,
    }


def _run_scenario(
    scenario: EvalScenario,
    indexes: EvalSearchIndexes,
    corpus: list[tuple[str, str, str]],
    cases: list[dict[str, Any]],
    *,
    db_path: Path,
    fixture_path: Path,
    k: int,
    rerank_candidate_multiplier: int,
) -> dict[str, Any]:
    searcher = build_searcher(
        scenario,
        indexes,
        corpus,
        rerank_candidate_multiplier=rerank_candidate_multiplier,
    )
    summary = eval_retrieval.evaluate(cases, corpus, searcher, k=k)
    return {
        "name": scenario.name,
        "mode": scenario.mode,
        "rerank": scenario.rerank,
        "rerank_candidate_multiplier": max(rerank_candidate_multiplier, 1)
        if scenario.rerank
        else None,
        "db": str(db_path),
        "fixture": str(fixture_path),
        "k": k,
        "corpus_size": len(corpus),
        "evaluable": summary["evaluable"],
        "no_gold": summary["no_gold"],
        "recall_at_k": summary["recall_at_k"],
        "mrr": summary["mrr"],
        "group_metrics": summary["group_metrics"],
    }


def _select_best_result(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not results:
        return None
    best = max(
        results,
        key=lambda item: (
            float(item["recall_at_k"]),
            float(item["mrr"]),
            int(item["evaluable"]),
        ),
    )
    return {
        "name": best["name"],
        "recall_at_k": best["recall_at_k"],
        "mrr": best["mrr"],
    }


def print_matrix_report(payload: dict[str, Any]) -> None:
    metadata = payload["metadata"]
    print("=" * 72)
    print("  检索评测矩阵")
    print("=" * 72)
    print(f"  语料库:   {metadata['db']}（{metadata['corpus_size']} 条启用知识）")
    print(f"  标注集:   {metadata['fixture']}")
    print(f"  K:        {metadata['k']}")
    print("-" * 72)
    print("  scenario                 recall@k   mrr      evaluable   no_gold")
    for item in payload["results"]:
        print(
            "  {name:<24} {recall:<9} {mrr:<8} {evaluable:<10} {no_gold}".format(
                name=item["name"],
                recall=item["recall_at_k"],
                mrr=item["mrr"],
                evaluable=item["evaluable"],
                no_gold=item["no_gold"],
            )
        )
    best = payload.get("best")
    if best:
        print("-" * 72)
        print("  best: {name} recall@k={recall_at_k} mrr={mrr}".format(**best))
    print("=" * 72)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="离线检索评测矩阵报告")
    parser.add_argument(
        "--db",
        default="",
        help="检索语料 SQLite 库；未指定时沿用 eval_retrieval 默认解析规则",
    )
    parser.add_argument(
        "--fixture",
        default=str(eval_retrieval.DEFAULT_FIXTURE_PATH),
        help="评测标注集路径",
    )
    parser.add_argument("--k", type=int, default=5, help="Recall@K 与召回截断的 K")
    parser.add_argument(
        "--rerank-candidate-multiplier",
        type=int,
        default=eval_retrieval.DEFAULT_RERANK_CANDIDATE_MULTIPLIER,
        help="rerank 场景候选池倍数，默认 3",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--json-out", default="", help="可选：写入 JSON 文件")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    db_path = eval_retrieval.resolve_db_path(args.db)
    if not db_path.exists():
        print(f"[ERROR] 语料库不存在: {db_path}", file=sys.stderr)
        return 1

    try:
        payload = run_matrix(
            db_path=db_path,
            fixture_path=Path(args.fixture),
            k=args.k,
            rerank_candidate_multiplier=args.rerank_candidate_multiplier,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_matrix_report(payload)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        print(f"[INFO] 矩阵报告已写入 {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
