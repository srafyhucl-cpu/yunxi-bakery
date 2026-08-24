from __future__ import annotations

import importlib.util
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from types import ModuleType


def load_matrix_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "report_retrieval_eval_matrix.py"
    )
    spec = importlib.util.spec_from_file_location(
        "report_retrieval_eval_matrix",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["report_retrieval_eval_matrix"] = module
    spec.loader.exec_module(module)
    return module


def create_eval_db(db_path: Path) -> None:
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            "CREATE TABLE knowledge_base ("
            "id INTEGER, youzan_item_id TEXT, title TEXT, content TEXT, is_active INTEGER)"
        )
        conn.executemany(
            "INSERT INTO knowledge_base VALUES (?, ?, ?, ?, ?)",
            [
                (1, "delivery", "配送范围", "三公里内可配送", 1),
                (2, "refund", "退款规则", "未制作可退款", 1),
            ],
        )


def create_fixture(fixture_path: Path) -> None:
    fixture_path.write_text(
        """
{
  "cases": [
    {
      "id": "delivery",
      "group": "delivery",
      "query": "配送",
      "relevant": [["配送"]]
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )


def test_run_matrix_reports_all_scenarios(tmp_path: Path, monkeypatch) -> None:
    matrix = load_matrix_module()
    db_path = tmp_path / "eval.db"
    fixture_path = tmp_path / "fixture.json"
    create_eval_db(db_path)
    create_fixture(fixture_path)
    build_calls: list[tuple[str, int]] = []

    class StubEmbeddingSearcher:
        def build(self, corpus: list[tuple[str, str, str]]) -> None:
            build_calls.append(("vector", len(corpus)))

        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            return [("delivery", 1.0)]

    class StubBM25Searcher:
        def build(self, corpus: list[tuple[str, str, str]]) -> None:
            build_calls.append(("bm25", len(corpus)))

        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            return [("delivery", 1.0)]

    monkeypatch.setattr(
        matrix.eval_retrieval, "EmbeddingSearcher", StubEmbeddingSearcher
    )
    monkeypatch.setattr(matrix.eval_retrieval, "BM25Searcher", StubBM25Searcher)

    payload = matrix.run_matrix(
        db_path=db_path,
        fixture_path=fixture_path,
        k=1,
        rerank_candidate_multiplier=2,
    )

    assert [item["name"] for item in payload["results"]] == [
        "vector",
        "hybrid",
        "planned-hybrid",
        "planned-hybrid+rerank",
    ]
    assert payload["metadata"]["corpus_size"] == 2
    assert payload["best"]["name"] == "vector"
    assert build_calls.count(("vector", 2)) == 1
    assert build_calls.count(("bm25", 2)) == 1


def test_select_best_result_prefers_recall_then_mrr() -> None:
    matrix = load_matrix_module()
    results = [
        {"name": "vector", "recall_at_k": 0.5, "mrr": 1.0, "evaluable": 2},
        {"name": "hybrid", "recall_at_k": 1.0, "mrr": 0.1, "evaluable": 2},
        {"name": "planned", "recall_at_k": 1.0, "mrr": 0.8, "evaluable": 2},
    ]

    assert matrix._select_best_result(results) == {
        "name": "planned",
        "recall_at_k": 1.0,
        "mrr": 0.8,
    }


def test_main_returns_error_when_db_missing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    matrix = load_matrix_module()
    missing_db = tmp_path / "missing.db"
    monkeypatch.setattr(
        matrix.eval_retrieval, "resolve_db_path", lambda _arg: missing_db
    )

    exit_code = matrix.main(["--db", str(missing_db)])

    assert exit_code == 1
    assert "语料库不存在" in capsys.readouterr().err
