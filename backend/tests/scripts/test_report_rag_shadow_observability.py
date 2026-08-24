from __future__ import annotations

import json
from pathlib import Path

from scripts import report_rag_shadow_observability as observability


def _shadow_payload() -> dict[str, object]:
    return {
        "metadata": {
            "db": "data/bot.db",
            "fixture": "tests/fixtures/customer_rag_golden_cases.json",
            "k": 5,
            "corpus_size": 400,
            "total_cases": 2,
            "configured_rag_retrieval_mode": "hybrid",
            "baseline": "hybrid",
            "candidates": ["planned-hybrid", "planned-hybrid+rerank"],
        },
        "baseline": {
            "name": "hybrid",
            "recall_at_k": 0.98,
            "mrr": 0.88,
            "evaluable": 2,
            "no_gold": 0,
        },
        "candidates": [
            {
                "name": "planned-hybrid",
                "recall_at_k": 0.98,
                "mrr": 0.88,
                "evaluable": 2,
                "no_gold": 0,
                "delta_recall_at_k": 0.0,
                "delta_mrr": 0.0,
            },
            {
                "name": "planned-hybrid+rerank",
                "recall_at_k": 0.95,
                "mrr": 0.89,
                "evaluable": 2,
                "no_gold": 0,
                "delta_recall_at_k": -0.03,
                "delta_mrr": 0.01,
            },
        ],
        "case_diffs": [
            {
                "id": "case-1",
                "group": "inventory",
                "query": "用户原文不应默认输出",
                "candidates": [
                    {"name": "planned-hybrid", "changed": False},
                    {"name": "planned-hybrid+rerank", "changed": True},
                ],
            },
            {
                "id": "case-2",
                "group": "refund",
                "query": "另一条用户原文",
                "candidates": [
                    {"name": "planned-hybrid", "changed": False},
                    {"name": "planned-hybrid+rerank", "changed": False},
                ],
            },
        ],
    }


def test_shadow_observability_summarizes_decisions_without_query(monkeypatch) -> None:
    monkeypatch.setattr(
        observability.shadow_compare,
        "run_shadow_compare",
        lambda **_kwargs: _shadow_payload(),
    )

    report = observability.build_rag_shadow_observability_report(
        db_path=Path("data/bot.db"),
        fixture_path=Path("tests/fixtures/customer_rag_golden_cases.json"),
    )

    assert report["status"] == "passed"
    assert report["boundaries"]["contains_user_query_text"] is False
    assert "case_diffs" not in report
    assert report["case_diff_summary"]["changed_by_group"] == {"inventory": 1}
    assert report["candidates"][0]["decision"]["status"] == "shadow_passed"
    assert report["candidates"][1]["decision"]["status"] == "blocked"
    assert "keep_below_baseline_rag_candidates_shadow_only" in report["missing_actions"]
    assert "用户原文不应默认输出" not in json.dumps(report, ensure_ascii=False)


def test_shadow_observability_can_include_case_diffs(monkeypatch) -> None:
    monkeypatch.setattr(
        observability.shadow_compare,
        "run_shadow_compare",
        lambda **_kwargs: _shadow_payload(),
    )

    report = observability.build_rag_shadow_observability_report(
        db_path=Path("data/bot.db"),
        fixture_path=Path("tests/fixtures/customer_rag_golden_cases.json"),
        include_case_diffs=True,
    )

    assert report["boundaries"]["contains_user_query_text"] is True
    assert report["case_diffs"][0]["query"] == "用户原文不应默认输出"


def test_shadow_observability_fails_without_evaluable_baseline(monkeypatch) -> None:
    payload = _shadow_payload()
    payload["baseline"] = {
        **payload["baseline"],
        "recall_at_k": 0.0,
        "evaluable": 0,
    }
    monkeypatch.setattr(
        observability.shadow_compare,
        "run_shadow_compare",
        lambda **_kwargs: payload,
    )

    report = observability.build_rag_shadow_observability_report(
        db_path=Path("data/bot.db"),
        fixture_path=Path("tests/fixtures/customer_rag_golden_cases.json"),
    )

    assert report["status"] == "failed"
    assert report["assertions"]["baseline.evaluable_positive"] is False
    assert report["assertions"]["baseline.recall_positive"] is False


def test_shadow_observability_cli_writes_json(monkeypatch, tmp_path: Path) -> None:
    output_path = tmp_path / "shadow.json"
    monkeypatch.setattr(
        observability.eval_retrieval, "resolve_db_path", lambda _db: tmp_path
    )
    monkeypatch.setattr(
        observability.shadow_compare,
        "run_shadow_compare",
        lambda **_kwargs: _shadow_payload(),
    )

    exit_code = observability.main(
        [
            "--db",
            str(tmp_path),
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["candidates"][1]["decision"]["hot_path_action"] == "keep_shadow_only"
