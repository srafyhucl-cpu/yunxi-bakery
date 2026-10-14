"""RAG 检索 shadow compare 报告。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts import eval_retrieval  # noqa: E402
from scripts import report_retrieval_eval_matrix as eval_matrix  # noqa: E402


DEFAULT_BASELINE = eval_matrix.EvalScenario(eval_retrieval.MODE_HYBRID)
DEFAULT_CANDIDATES = (
    eval_matrix.EvalScenario(eval_retrieval.MODE_PLANNED_HYBRID),
    eval_matrix.EvalScenario(eval_retrieval.MODE_PLANNED_HYBRID, rerank=True),
)
SCENARIO_ALIASES = {
    eval_retrieval.MODE_HYBRID: eval_matrix.EvalScenario(
        eval_retrieval.MODE_HYBRID,
    ),
    eval_retrieval.MODE_PLANNED_HYBRID: eval_matrix.EvalScenario(
        eval_retrieval.MODE_PLANNED_HYBRID,
    ),
    "planned-hybrid-rerank": eval_matrix.EvalScenario(
        eval_retrieval.MODE_PLANNED_HYBRID,
        rerank=True,
    ),
    "planned-hybrid+rerank": eval_matrix.EvalScenario(
        eval_retrieval.MODE_PLANNED_HYBRID,
        rerank=True,
    ),
}


@dataclass(frozen=True)
class ShadowSearchResult:
    name: str
    summary: dict[str, Any]
    top_keys_by_case: dict[str, list[str]]


def run_shadow_compare(
    *,
    db_path: Path,
    fixture_path: Path,
    k: int,
    rerank_candidate_multiplier: int,
    baseline: eval_matrix.EvalScenario = DEFAULT_BASELINE,
    candidates: tuple[eval_matrix.EvalScenario, ...] = DEFAULT_CANDIDATES,
) -> dict[str, Any]:
    corpus = eval_retrieval.load_corpus(db_path)
    if not corpus:
        raise ValueError(f"{db_path} 中无启用知识，无法评测")
    cases = eval_retrieval.load_eval_set(fixture_path)
    scenarios = (baseline, *candidates)
    indexes = eval_matrix.build_search_indexes(scenarios, corpus)
    baseline_result = _run_shadow_scenario(
        baseline,
        indexes,
        corpus,
        cases,
        k=k,
        rerank_candidate_multiplier=rerank_candidate_multiplier,
    )
    candidate_results = tuple(
        _run_shadow_scenario(
            candidate,
            indexes,
            corpus,
            cases,
            k=k,
            rerank_candidate_multiplier=rerank_candidate_multiplier,
        )
        for candidate in candidates
    )
    return {
        "metadata": {
            "db": str(db_path),
            "fixture": str(fixture_path),
            "k": k,
            "corpus_size": len(corpus),
            "total_cases": len(cases),
            "configured_rag_retrieval_mode": _current_rag_retrieval_mode(),
            "baseline": baseline.name,
            "candidates": [candidate.name for candidate in candidates],
        },
        "baseline": _summary_payload(baseline_result),
        "candidates": [
            _candidate_payload(baseline_result, candidate_result)
            for candidate_result in candidate_results
        ],
        "case_diffs": _build_case_diffs(
            cases,
            corpus,
            baseline_result,
            candidate_results,
        ),
    }


def parse_shadow_scenario(value: str) -> eval_matrix.EvalScenario:
    normalized_value = value.strip().lower()
    if normalized_value in SCENARIO_ALIASES:
        return SCENARIO_ALIASES[normalized_value]
    allowed_values = ", ".join(sorted(SCENARIO_ALIASES))
    msg = f"未知 shadow compare 检索模式: {value}；可选值: {allowed_values}"
    raise argparse.ArgumentTypeError(msg)


def _current_rag_retrieval_mode() -> str:
    return os.getenv("RAG_RETRIEVAL_MODE", eval_retrieval.MODE_HYBRID).strip().lower()


def _run_shadow_scenario(
    scenario: eval_matrix.EvalScenario,
    indexes: eval_matrix.EvalSearchIndexes,
    corpus: list[tuple[str, str, str]],
    cases: list[dict[str, Any]],
    *,
    k: int,
    rerank_candidate_multiplier: int,
) -> ShadowSearchResult:
    searcher = eval_matrix.build_searcher(
        scenario,
        indexes,
        corpus,
        rerank_candidate_multiplier=rerank_candidate_multiplier,
    )
    summary = eval_retrieval.evaluate(cases, corpus, searcher, k=k)
    return ShadowSearchResult(
        name=scenario.name,
        summary=summary,
        top_keys_by_case={
            str(case["id"]): [
                key for key, _score in searcher.search(str(case["query"]), limit=k)
            ]
            for case in cases
            if "id" in case and "query" in case
        },
    )


def _summary_payload(result: ShadowSearchResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "recall_at_k": result.summary["recall_at_k"],
        "mrr": result.summary["mrr"],
        "evaluable": result.summary["evaluable"],
        "no_gold": result.summary["no_gold"],
    }


def _candidate_payload(
    baseline: ShadowSearchResult,
    candidate: ShadowSearchResult,
) -> dict[str, Any]:
    payload = _summary_payload(candidate)
    payload["delta_recall_at_k"] = round(
        float(candidate.summary["recall_at_k"])
        - float(baseline.summary["recall_at_k"]),
        4,
    )
    payload["delta_mrr"] = round(
        float(candidate.summary["mrr"]) - float(baseline.summary["mrr"]),
        4,
    )
    return payload


def _build_case_diffs(
    cases: list[dict[str, Any]],
    corpus: list[tuple[str, str, str]],
    baseline: ShadowSearchResult,
    candidates: tuple[ShadowSearchResult, ...],
) -> list[dict[str, Any]]:
    title_by_key = {key: title for key, title, _content in corpus}
    return [
        _case_diff_payload(case, title_by_key, baseline, candidates)
        for case in cases
        if "id" in case and "query" in case
    ]


def _case_diff_payload(
    case: dict[str, Any],
    title_by_key: dict[str, str],
    baseline: ShadowSearchResult,
    candidates: tuple[ShadowSearchResult, ...],
) -> dict[str, Any]:
    case_id = str(case["id"])
    baseline_keys = baseline.top_keys_by_case.get(case_id, [])
    return {
        "id": case_id,
        "group": str(case.get("group", "ungrouped") or "ungrouped"),
        "query": str(case["query"]),
        "baseline": _top_key_payload(baseline.name, baseline_keys, title_by_key),
        "candidates": [
            _candidate_case_payload(candidate, baseline_keys, case_id, title_by_key)
            for candidate in candidates
        ],
    }


def _candidate_case_payload(
    candidate: ShadowSearchResult,
    baseline_keys: list[str],
    case_id: str,
    title_by_key: dict[str, str],
) -> dict[str, Any]:
    candidate_keys = candidate.top_keys_by_case.get(case_id, [])
    candidate_payload = _top_key_payload(candidate.name, candidate_keys, title_by_key)
    candidate_payload["changed"] = candidate_keys != baseline_keys
    candidate_payload["overlap_count"] = len(set(candidate_keys) & set(baseline_keys))
    return candidate_payload


def _top_key_payload(
    name: str,
    keys: list[str],
    title_by_key: dict[str, str],
) -> dict[str, Any]:
    return {
        "name": name,
        "top_keys": keys,
        "top_titles": [title_by_key.get(key, key) for key in keys],
    }


def print_shadow_summary(payload: dict[str, Any]) -> None:
    metadata = payload["metadata"]
    print("retrieval_shadow_compare")
    print(
        f"db={metadata['db']} fixture={metadata['fixture']} "
        f"k={metadata['k']} corpus={metadata['corpus_size']}"
    )
    print(f"configured_rag_retrieval_mode={metadata['configured_rag_retrieval_mode']}")
    baseline = payload["baseline"]
    print(
        "baseline "
        f"name={baseline['name']} recall={baseline['recall_at_k']} "
        f"mrr={baseline['mrr']} evaluable={baseline['evaluable']}"
    )
    for candidate in payload["candidates"]:
        print(
            "candidate "
            f"name={candidate['name']} recall={candidate['recall_at_k']} "
            f"mrr={candidate['mrr']} "
            f"delta_recall={candidate['delta_recall_at_k']} "
            f"delta_mrr={candidate['delta_mrr']}"
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAG 检索 shadow compare 报告")
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
    parser.add_argument("--k", type=int, default=5, help="Top-K 截断")
    parser.add_argument(
        "--rerank-candidate-multiplier",
        type=int,
        default=eval_retrieval.DEFAULT_RERANK_CANDIDATE_MULTIPLIER,
        help="rerank 场景候选池倍数，默认 3",
    )
    parser.add_argument(
        "--baseline-mode",
        type=parse_shadow_scenario,
        default=DEFAULT_BASELINE,
        help="baseline 检索模式，默认 hybrid",
    )
    parser.add_argument(
        "--candidate-mode",
        type=parse_shadow_scenario,
        action="append",
        default=None,
        help=(
            "候选检索模式，可重复传入；"
            "支持 planned-hybrid、planned-hybrid-rerank、planned-hybrid+rerank"
        ),
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--json-out", default="", help="可选：写入 JSON 文件")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(sys.argv[1:] if argv is None else argv)
    db_path = eval_retrieval.resolve_db_path(args.db)
    if not db_path.exists():
        print(f"[ERROR] 语料库不存在: {db_path}", file=sys.stderr)
        return 1
    try:
        payload = run_shadow_compare(
            db_path=db_path,
            fixture_path=Path(args.fixture),
            k=args.k,
            rerank_candidate_multiplier=args.rerank_candidate_multiplier,
            baseline=args.baseline_mode,
            candidates=tuple(args.candidate_mode or DEFAULT_CANDIDATES),
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_shadow_summary(payload)

    if args.json_out:
        output_path = Path(args.json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        print(f"[INFO] shadow compare 报告已写入 {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
