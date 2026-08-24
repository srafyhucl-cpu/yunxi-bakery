from __future__ import annotations

import importlib.util
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from types import ModuleType

import pytest


def load_shadow_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "report_retrieval_shadow_compare.py"
    )
    spec = importlib.util.spec_from_file_location(
        "report_retrieval_shadow_compare",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["report_retrieval_shadow_compare"] = module
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


def test_run_shadow_compare_reports_candidate_diffs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    shadow = load_shadow_module()
    db_path = tmp_path / "eval.db"
    fixture_path = tmp_path / "fixture.json"
    create_eval_db(db_path)
    create_fixture(fixture_path)
    build_calls: list[tuple[str, int]] = []

    class StubEmbeddingSearcher:
        def build(self, corpus: list[tuple[str, str, str]]) -> None:
            build_calls.append(("vector", len(corpus)))

        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            return [("refund", 1.0)]

    class StubBM25Searcher:
        def build(self, corpus: list[tuple[str, str, str]]) -> None:
            build_calls.append(("bm25", len(corpus)))

        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            return [("delivery", 1.0)]

    monkeypatch.setattr(
        shadow.eval_retrieval,
        "EmbeddingSearcher",
        StubEmbeddingSearcher,
    )
    monkeypatch.setattr(shadow.eval_retrieval, "BM25Searcher", StubBM25Searcher)

    payload = shadow.run_shadow_compare(
        db_path=db_path,
        fixture_path=fixture_path,
        k=2,
        rerank_candidate_multiplier=2,
    )

    assert payload["metadata"]["baseline"] == "hybrid"
    assert payload["metadata"]["candidates"] == [
        "planned-hybrid",
        "planned-hybrid+rerank",
    ]
    assert payload["baseline"]["recall_at_k"] == 1.0
    assert payload["candidates"][0]["delta_recall_at_k"] == 0.0
    assert payload["case_diffs"][0]["baseline"]["top_keys"] == [
        "refund",
        "delivery",
    ]
    assert payload["case_diffs"][0]["candidates"][0]["overlap_count"] == 2
    assert build_calls.count(("vector", 2)) == 1
    assert build_calls.count(("bm25", 2)) == 1


def test_run_shadow_compare_accepts_explicit_modes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    shadow = load_shadow_module()
    db_path = tmp_path / "eval.db"
    fixture_path = tmp_path / "fixture.json"
    create_eval_db(db_path)
    create_fixture(fixture_path)
    monkeypatch.setenv("RAG_RETRIEVAL_MODE", " planned-hybrid ")

    class StubEmbeddingSearcher:
        def build(self, corpus: list[tuple[str, str, str]]) -> None:
            return None

        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            return [("delivery", 1.0)]

    class StubBM25Searcher:
        def build(self, corpus: list[tuple[str, str, str]]) -> None:
            return None

        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            return [("delivery", 1.0)]

    monkeypatch.setattr(
        shadow.eval_retrieval,
        "EmbeddingSearcher",
        StubEmbeddingSearcher,
    )
    monkeypatch.setattr(shadow.eval_retrieval, "BM25Searcher", StubBM25Searcher)

    payload = shadow.run_shadow_compare(
        db_path=db_path,
        fixture_path=fixture_path,
        k=2,
        rerank_candidate_multiplier=2,
        baseline=shadow.parse_shadow_scenario("hybrid"),
        candidates=(shadow.parse_shadow_scenario("planned-hybrid-rerank"),),
    )

    assert payload["metadata"]["configured_rag_retrieval_mode"] == "planned-hybrid"
    assert payload["metadata"]["baseline"] == "hybrid"
    assert payload["metadata"]["candidates"] == ["planned-hybrid+rerank"]
    assert payload["candidates"][0]["name"] == "planned-hybrid+rerank"


def test_parse_shadow_scenario_rejects_unknown_mode() -> None:
    shadow = load_shadow_module()

    with pytest.raises(Exception, match="未知 shadow compare 检索模式"):
        shadow.parse_shadow_scenario("unknown")


def test_main_returns_error_when_db_missing(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    shadow = load_shadow_module()
    missing_db = tmp_path / "missing.db"
    monkeypatch.setattr(
        shadow.eval_retrieval,
        "resolve_db_path",
        lambda _arg: missing_db,
    )

    exit_code = shadow.main(["--db", str(missing_db)])

    assert exit_code == 1
    assert "语料库不存在" in capsys.readouterr().err


def test_main_writes_json_out_with_missing_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    shadow = load_shadow_module()
    db_path = tmp_path / "eval.db"
    fixture_path = tmp_path / "fixture.json"
    output_path = tmp_path / "reports" / "shadow" / "latest.json"
    create_eval_db(db_path)
    create_fixture(fixture_path)

    class StubEmbeddingSearcher:
        def build(self, corpus: list[tuple[str, str, str]]) -> None:
            return None

        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            return [("delivery", 1.0)]

    class StubBM25Searcher:
        def build(self, corpus: list[tuple[str, str, str]]) -> None:
            return None

        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            return [("delivery", 1.0)]

    monkeypatch.setattr(
        shadow.eval_retrieval,
        "EmbeddingSearcher",
        StubEmbeddingSearcher,
    )
    monkeypatch.setattr(shadow.eval_retrieval, "BM25Searcher", StubBM25Searcher)

    exit_code = shadow.main(
        [
            "--db",
            str(db_path),
            "--fixture",
            str(fixture_path),
            "--json-out",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
