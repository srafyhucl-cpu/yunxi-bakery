"""RAG shadow 观测报告。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from app.service.agents.evaluation import write_json_report  # noqa: E402
from scripts import eval_retrieval  # noqa: E402
from scripts import report_retrieval_shadow_compare as shadow_compare  # noqa: E402

DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "retrieval-shadow" / "rag-shadow-observability.json"
)
DEFAULT_DB_PATH = ROOT_DIR / "data" / "bot.db"
DEFAULT_FIXTURE_PATH = (
    ROOT_DIR / "tests" / "fixtures" / "customer_rag_golden_cases.json"
)
DEFAULT_K = 5
DEFAULT_MIN_RECALL_DELTA = 0.0
DEFAULT_MIN_MRR_DELTA = 0.0


def build_rag_shadow_observability_report(
    *,
    db_path: Path,
    fixture_path: Path,
    k: int = DEFAULT_K,
    min_recall_delta: float = DEFAULT_MIN_RECALL_DELTA,
    min_mrr_delta: float = DEFAULT_MIN_MRR_DELTA,
    include_case_diffs: bool = False,
) -> dict[str, object]:
    shadow_payload = shadow_compare.run_shadow_compare(
        db_path=db_path,
        fixture_path=fixture_path,
        k=k,
        rerank_candidate_multiplier=eval_retrieval.DEFAULT_RERANK_CANDIDATE_MULTIPLIER,
    )
    candidates = build_candidate_summaries(
        shadow_payload,
        min_recall_delta=min_recall_delta,
        min_mrr_delta=min_mrr_delta,
    )
    assertions = build_assertions(shadow_payload=shadow_payload, candidates=candidates)
    failed = sum(1 for passed in assertions.values() if not passed)
    report: dict[str, object] = {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "failed": failed,
        "metadata": sanitize_metadata(shadow_payload["metadata"]),
        "thresholds": {
            "min_recall_delta": min_recall_delta,
            "min_mrr_delta": min_mrr_delta,
        },
        "baseline": shadow_payload["baseline"],
        "candidates": candidates,
        "assertions": assertions,
        "missing_actions": build_missing_actions(candidates),
        "boundaries": {
            "production_hot_path_changed": False,
            "rag_retrieval_mode_changed": False,
            "external_llm_called": False,
            "business_database_written": False,
            "contains_user_query_text": include_case_diffs,
        },
    }
    if include_case_diffs:
        report["case_diffs"] = shadow_payload["case_diffs"]
    else:
        report["case_diff_summary"] = build_case_diff_summary(shadow_payload)
    return report


def sanitize_metadata(metadata: dict[str, Any]) -> dict[str, object]:
    return {
        "db": metadata["db"],
        "fixture": metadata["fixture"],
        "k": metadata["k"],
        "corpus_size": metadata["corpus_size"],
        "total_cases": metadata["total_cases"],
        "configured_rag_retrieval_mode": metadata["configured_rag_retrieval_mode"],
        "baseline": metadata["baseline"],
        "candidates": metadata["candidates"],
    }


def build_candidate_summaries(
    shadow_payload: dict[str, Any],
    *,
    min_recall_delta: float,
    min_mrr_delta: float,
) -> list[dict[str, object]]:
    changed_counts = count_changed_cases_by_candidate(shadow_payload)
    return [
        {
            **candidate,
            "changed_case_count": changed_counts.get(candidate["name"], 0),
            "decision": decide_candidate(
                candidate,
                min_recall_delta=min_recall_delta,
                min_mrr_delta=min_mrr_delta,
            ),
        }
        for candidate in shadow_payload["candidates"]
    ]


def count_changed_cases_by_candidate(
    shadow_payload: dict[str, Any],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case_diff in shadow_payload["case_diffs"]:
        for candidate in case_diff["candidates"]:
            if candidate["changed"]:
                name = str(candidate["name"])
                counts[name] = counts.get(name, 0) + 1
    return counts


def decide_candidate(
    candidate: dict[str, Any],
    *,
    min_recall_delta: float,
    min_mrr_delta: float,
) -> dict[str, object]:
    recall_ok = float(candidate["delta_recall_at_k"]) >= min_recall_delta
    mrr_ok = float(candidate["delta_mrr"]) >= min_mrr_delta
    allowed = recall_ok and mrr_ok
    if allowed:
        return {
            "status": "shadow_passed",
            "hot_path_action": "eligible_for_controlled_gray_release",
            "reason": "candidate_not_below_baseline",
        }
    return {
        "status": "blocked",
        "hot_path_action": "keep_shadow_only",
        "reason": "candidate_below_baseline",
    }


def build_case_diff_summary(shadow_payload: dict[str, Any]) -> dict[str, object]:
    changed_by_group: dict[str, int] = {}
    changed_total = 0
    for case_diff in shadow_payload["case_diffs"]:
        if any(candidate["changed"] for candidate in case_diff["candidates"]):
            group = str(case_diff.get("group", "ungrouped") or "ungrouped")
            changed_total += 1
            changed_by_group[group] = changed_by_group.get(group, 0) + 1
    return {
        "total_cases": len(shadow_payload["case_diffs"]),
        "changed_case_count": changed_total,
        "changed_by_group": changed_by_group,
    }


def build_assertions(
    *,
    shadow_payload: dict[str, Any],
    candidates: list[dict[str, object]],
) -> dict[str, bool]:
    baseline = shadow_payload["baseline"]
    metadata = shadow_payload["metadata"]
    return {
        "shadow_compare.completed": True,
        "baseline.evaluable_positive": int(baseline["evaluable"]) > 0,
        "baseline.recall_positive": float(baseline["recall_at_k"]) > 0,
        "configured_mode.recorded": bool(metadata["configured_rag_retrieval_mode"]),
        "candidate_decisions.present": all("decision" in item for item in candidates),
    }


def build_missing_actions(candidates: list[dict[str, object]]) -> list[str]:
    actions = []
    if any(item["decision"]["status"] == "blocked" for item in candidates):
        actions.append("keep_below_baseline_rag_candidates_shadow_only")
    if not any(item["decision"]["status"] == "shadow_passed" for item in candidates):
        actions.append("collect_more_shadow_compare_before_rag_gray_release")
    return actions


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build RAG shadow observability report"
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="检索语料 SQLite 库，默认 data/bot.db",
    )
    parser.add_argument(
        "--fixture",
        default=str(DEFAULT_FIXTURE_PATH),
        help="评测标注集路径，默认客户 RAG golden cases",
    )
    parser.add_argument("--k", type=int, default=DEFAULT_K, help="Top-K 截断")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="写入 RAG shadow 观测 JSON 路径",
    )
    parser.add_argument(
        "--include-case-diffs",
        action="store_true",
        help="输出完整 case diff；默认只输出不含 query 原文的汇总",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    db_path = eval_retrieval.resolve_db_path(args.db)
    if not db_path.exists():
        print(f"[ERROR] 语料库不存在: {db_path}", file=sys.stderr)
        return 1
    try:
        report = build_rag_shadow_observability_report(
            db_path=db_path,
            fixture_path=Path(args.fixture),
            k=args.k,
            include_case_diffs=args.include_case_diffs,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    if args.json_out is not None:
        write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "rag_shadow_observability "
            f"status={report['status']} failed={report['failed']} "
            f"baseline={report['baseline']['name']} "
            f"candidates={len(report['candidates'])}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_text_report(report: dict[str, object]) -> None:
    print("rag_shadow_observability")
    print(
        f"status={report['status']} failed={report['failed']} "
        f"baseline={report['baseline']['name']}"
    )
    for candidate in report["candidates"]:
        decision = candidate["decision"]
        print(
            "candidate "
            f"name={candidate['name']} "
            f"delta_recall={candidate['delta_recall_at_k']} "
            f"delta_mrr={candidate['delta_mrr']} "
            f"decision={decision['status']}"
        )
    for action in report["missing_actions"]:
        print(f"NEXT {action}")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
