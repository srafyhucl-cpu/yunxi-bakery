from __future__ import annotations

import importlib.util
import sqlite3
from contextlib import closing
from pathlib import Path
from types import ModuleType, SimpleNamespace


def load_eval_module() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "eval_retrieval.py"
    spec = importlib.util.spec_from_file_location("eval_retrieval", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_db_path_prefers_explicit_path(tmp_path: Path) -> None:
    eval_retrieval = load_eval_module()
    explicit_db = tmp_path / "custom.db"

    assert eval_retrieval.resolve_db_path(str(explicit_db)) == explicit_db


def test_resolve_db_path_uses_safe_default_without_raw_fallback(tmp_path: Path) -> None:
    eval_retrieval = load_eval_module()
    default_db = tmp_path / "eval.db"
    eval_retrieval.DEFAULT_EVALUATION_DB = default_db

    assert eval_retrieval.resolve_db_path("") == default_db
    assert not hasattr(eval_retrieval, "LOCAL_RAW_SNAPSHOT_DB")


def test_load_corpus_builds_stable_keys(tmp_path: Path) -> None:
    eval_retrieval = load_eval_module()
    db_path = tmp_path / "eval.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            "CREATE TABLE knowledge_base ("
            "id INTEGER, youzan_item_id TEXT, title TEXT, content TEXT, is_active INTEGER)"
        )
        conn.executemany(
            "INSERT INTO knowledge_base VALUES (?, ?, ?, ?, ?)",
            [
                (1, "1001", "提拉米苏", "经典蛋糕", 1),
                (2, None, "配送规则", "同城配送", 1),
                (3, "1003", "下架商品", "不可售", 0),
            ],
        )

    assert eval_retrieval.load_corpus(db_path) == [
        ("1001", "提拉米苏", "经典蛋糕"),
        ("kb_2", "配送规则", "同城配送"),
    ]


def test_load_eval_set_accepts_custom_fixture(tmp_path: Path) -> None:
    eval_retrieval = load_eval_module()
    fixture_path = tmp_path / "customer_cases.json"
    fixture_path.write_text(
        """
{
  "cases": [
    {
      "id": "customer-delivery",
      "group": "delivery",
      "query": "你们送货吗",
      "relevant": [["配送"]]
    },
    {
      "id": "placeholder"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    cases = eval_retrieval.load_eval_set(fixture_path)

    assert [case["id"] for case in cases] == ["customer-delivery"]
    assert cases[0]["group"] == "delivery"


def test_evaluate_calculates_recall_mrr_and_no_gold() -> None:
    eval_retrieval = load_eval_module()

    class StubSearcher:
        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            results = {
                "命中第二名": [("miss", 0.9), ("p1", 0.8)],
                "未命中": [("miss", 0.9)],
                "无目标": [("p1", 0.8)],
            }
            return results[query][:limit]

    cases = [
        {"id": "hit", "query": "命中第二名", "relevant": [["提拉米苏"]]},
        {"id": "miss", "query": "未命中", "relevant": [["草莓"]]},
        {"id": "no-gold", "query": "无目标", "relevant": [["马卡龙"]]},
    ]
    corpus = [("p1", "提拉米苏", "经典蛋糕"), ("p2", "草莓蛋糕", "当季限定")]

    summary = eval_retrieval.evaluate(cases, corpus, StubSearcher(), k=2)

    assert summary["evaluable"] == 2
    assert summary["no_gold"] == 1
    assert summary["recall_at_k"] == 0.5
    assert summary["mrr"] == 0.25


def test_evaluate_reports_group_metrics() -> None:
    eval_retrieval = load_eval_module()

    class StubSearcher:
        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            results = {
                "送货": [("delivery-hit", 0.9)],
                "退款": [("miss", 0.9)],
                "人工": [("delivery-hit", 0.9)],
            }
            return results[query][:limit]

    cases = [
        {
            "id": "delivery-hit",
            "group": "delivery",
            "query": "送货",
            "relevant": [["配送"]],
        },
        {
            "id": "refund-miss",
            "group": "refund_after_sales",
            "query": "退款",
            "relevant": [["售后"]],
        },
        {
            "id": "transfer-no-gold",
            "group": "human_transfer",
            "query": "人工",
            "relevant": [["人工"]],
        },
    ]
    corpus = [
        ("delivery-hit", "配送规则", "同城配送"),
        ("refund-hit", "售后规则", "售后处理"),
    ]

    summary = eval_retrieval.evaluate(cases, corpus, StubSearcher(), k=2)

    assert summary["group_metrics"]["delivery"]["recall_at_k"] == 1.0
    assert summary["group_metrics"]["refund_after_sales"]["recall_at_k"] == 0.0
    assert summary["group_metrics"]["human_transfer"]["no_gold"] == 1


def test_planned_query_searcher_expands_and_dedupes_results() -> None:
    eval_retrieval = load_eval_module()

    class StubSearcher:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            self.calls.append((query, limit))
            results = {
                "我下错单了，可以取消退款吗": [("cancel-policy", 0.9)],
                "退款规则 售后政策": [
                    ("cancel-policy", 0.8),
                    ("refund-policy", 0.7),
                ],
            }
            return results.get(query, [])[:limit]

    base_searcher = StubSearcher()
    searcher = eval_retrieval.PlannedQueryEvalSearcher(base_searcher)

    results = searcher.search("我下错单了，可以取消退款吗", limit=2)

    assert base_searcher.calls == [
        ("我下错单了，可以取消退款吗", 2),
        ("退款规则 售后政策", 2),
    ]
    assert results == [("cancel-policy", 0.9), ("refund-policy", 0.7)]


def test_planned_query_searcher_keeps_plain_query_when_no_expansion() -> None:
    eval_retrieval = load_eval_module()

    class StubSearcher:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            self.calls.append((query, limit))
            return [("plain-hit", 0.9)]

    base_searcher = StubSearcher()
    searcher = eval_retrieval.PlannedQueryEvalSearcher(base_searcher)

    assert searcher.search("提拉米苏", limit=3) == [("plain-hit", 0.9)]
    assert base_searcher.calls == [("提拉米苏", 3)]


def test_planned_query_searcher_falls_back_when_plan_has_no_variants(
    monkeypatch,
) -> None:
    eval_retrieval = load_eval_module()

    class StubSearcher:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            self.calls.append((query, limit))
            return [("blank-hit", 0.9)]

    monkeypatch.setattr(
        eval_retrieval,
        "build_customer_rag_query_plan",
        lambda query: SimpleNamespace(original_query=query, variants=()),
    )
    base_searcher = StubSearcher()
    searcher = eval_retrieval.PlannedQueryEvalSearcher(base_searcher)

    assert searcher.search("", limit=2) == [("blank-hit", 0.9)]
    assert base_searcher.calls == [("", 2)]


def test_planned_query_searcher_stops_after_limit_results() -> None:
    eval_retrieval = load_eval_module()

    class StubSearcher:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            self.calls.append((query, limit))
            results = {
                "可以退吗": [("refund-a", 0.9), ("refund-b", 0.8)],
                "退款规则 售后政策": [("refund-c", 0.7)],
            }
            return results.get(query, [])[:limit]

    base_searcher = StubSearcher()
    searcher = eval_retrieval.PlannedQueryEvalSearcher(base_searcher)

    assert searcher.search("可以退吗", limit=2) == [
        ("refund-a", 0.9),
        ("refund-b", 0.8),
    ]
    assert base_searcher.calls == [("可以退吗", 2)]


def test_rerank_eval_searcher_expands_candidates_and_reranks() -> None:
    eval_retrieval = load_eval_module()

    class StubSearcher:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            self.calls.append((query, limit))
            return [
                ("delivery", 0.9),
                ("refund", 0.8),
                ("bread", 0.7),
            ][:limit]

    corpus = [
        ("delivery", "配送范围", "三公里内可配送"),
        ("refund", "退款规则", "未制作可退款，已制作需人工确认"),
        ("bread", "吐司", "每日现烤"),
    ]
    base_searcher = StubSearcher()
    searcher = eval_retrieval.RerankEvalSearcher(
        base_searcher,
        corpus,
        candidate_multiplier=3,
    )

    results = searcher.search("可以退款吗", limit=1)

    assert base_searcher.calls == [("可以退款吗", 3)]
    assert results == [("refund", 1.0)]


def test_rerank_eval_searcher_keeps_multiplier_at_least_one() -> None:
    eval_retrieval = load_eval_module()

    class StubSearcher:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def search(self, query: str, limit: int) -> list[tuple[str, float]]:
            self.calls.append((query, limit))
            return [("refund", 0.9)]

    corpus = [("refund", "退款规则", "未制作可退款")]
    base_searcher = StubSearcher()
    searcher = eval_retrieval.RerankEvalSearcher(
        base_searcher,
        corpus,
        candidate_multiplier=0,
    )

    assert searcher.search("退款", limit=2) == [("refund", 2.0)]
    assert base_searcher.calls == [("退款", 2)]
