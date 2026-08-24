from __future__ import annotations

import json
from pathlib import Path

from scripts import report_rag_shadow_log_observability as log_observability


class _FakeSearcher:
    def __init__(self, keys: list[str]) -> None:
        self._keys = keys

    def search(self, query: str, limit: int) -> list[tuple[str, float]]:
        return [(key, 1.0) for key in self._keys[:limit]]


def _input_payload() -> dict[str, object]:
    return {
        "metadata": {
            "source_type": log_observability.REAL_SHADOW_LOG_SOURCE_TYPE,
            "contains_sensitive_data": False,
            "redaction_method": "tool_redaction_plus_manual_review",
            "redaction_reviewer": "reviewer_a",
            "redaction_reviewed_at": "2026-07-10",
            "raw_source_retention": "not_committed",
            "evidence_id": "E-RAG-SHADOW-001",
        },
        "records": [
            {
                "id": "log-1",
                "group": "inventory",
                "query": "脱敏库存咨询",
                "baseline_top_keys": ["kb_1", "kb_2"],
            }
        ],
    }


def _patch_shadow_search(monkeypatch) -> None:
    monkeypatch.setattr(
        log_observability.eval_retrieval,
        "load_corpus",
        lambda _db_path: [("kb_1", "title 1", "content 1")],
    )
    monkeypatch.setattr(
        log_observability.eval_matrix,
        "build_search_indexes",
        lambda _scenarios, _corpus: object(),
    )

    def fake_build_searcher(scenario, *_args, **_kwargs):
        if scenario.name == "hybrid":
            return _FakeSearcher(["kb_1", "kb_2"])
        if scenario.name == "planned-hybrid":
            return _FakeSearcher(["kb_1", "kb_2"])
        return _FakeSearcher(["kb_9", "kb_2"])

    monkeypatch.setattr(
        log_observability.eval_matrix,
        "build_searcher",
        fake_build_searcher,
    )


def test_missing_input_passes_readiness_without_claiming_ready() -> None:
    report = log_observability.build_rag_shadow_log_observability_report()

    assert report["status"] == "passed"
    assert report["shadow_log_ready"] is False
    assert "provide_redacted_rag_shadow_log_input" in report["missing_actions"]
    assert report["boundaries"]["contains_user_query_text"] is False


def test_missing_input_fails_when_required() -> None:
    report = log_observability.build_rag_shadow_log_observability_report(
        require_input=True
    )

    assert report["status"] == "failed"
    assert report["assertions"]["shadow_log.input_present"] is False


def test_shadow_log_input_runs_candidates_without_query_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_shadow_search(monkeypatch)
    input_path = tmp_path / "input.json"
    input_path.write_text(
        json.dumps(_input_payload(), ensure_ascii=False), encoding="utf-8"
    )

    report = log_observability.build_rag_shadow_log_observability_report(
        input_path=input_path,
        db_path=tmp_path / "bot.db",
    )

    assert report["status"] == "passed"
    assert report["shadow_log_ready"] is True
    assert report["summary"]["changed_by_candidate"] == {"planned-hybrid+rerank": 1}
    assert report["records"][0]["query_hash"]
    assert "query" not in report["records"][0]
    assert "脱敏库存咨询" not in json.dumps(report, ensure_ascii=False)


def test_shadow_log_input_can_include_queries(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_shadow_search(monkeypatch)
    input_path = tmp_path / "input.json"
    input_path.write_text(
        json.dumps(_input_payload(), ensure_ascii=False), encoding="utf-8"
    )

    report = log_observability.build_rag_shadow_log_observability_report(
        input_path=input_path,
        db_path=tmp_path / "bot.db",
        include_queries=True,
    )

    assert report["boundaries"]["contains_user_query_text"] is True
    assert report["records"][0]["query"] == "脱敏库存咨询"


def test_invalid_input_requires_desensitized_metadata(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    payload = _input_payload()
    payload["metadata"]["contains_sensitive_data"] = True
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = log_observability.build_rag_shadow_log_observability_report(
        input_path=input_path,
        db_path=tmp_path / "bot.db",
    )

    assert report["status"] == "failed"
    assert report["assertions"]["metadata.contains_sensitive_data_false"] is False
    assert "mark_shadow_log_input_as_desensitized" in report["missing_actions"]


def test_invalid_input_requires_redaction_proof(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    payload = _input_payload()
    payload["metadata"]["redaction_reviewer"] = "<脱敏审核人>"
    payload["metadata"]["redaction_reviewed_at"] = "not-a-date"
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = log_observability.build_rag_shadow_log_observability_report(
        input_path=input_path,
        db_path=tmp_path / "bot.db",
    )

    assert report["status"] == "failed"
    assert report["shadow_log_ready"] is False
    assert report["assertions"]["metadata.redaction_reviewer.present"] is False
    assert report["assertions"]["metadata.redaction_reviewed_at.iso_date"] is False
    assert "provide_shadow_log_redaction_reviewer" in report["missing_actions"]
    assert (
        "provide_shadow_log_redaction_reviewed_at_iso_date" in report["missing_actions"]
    )


def test_invalid_input_rejects_non_object_metadata_and_non_list_records(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text(
        json.dumps({"metadata": [], "records": {}}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = log_observability.build_rag_shadow_log_observability_report(
        input_path=input_path,
        db_path=tmp_path / "bot.db",
    )

    assert report["status"] == "failed"
    assert report["shadow_log_ready"] is False
    assert report["assertions"]["records.present"] is False
    assert "provide_redacted_rag_shadow_log_input" in report["missing_actions"]


def test_invalid_input_rejects_obvious_sensitive_query(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    payload = _input_payload()
    payload["records"][0]["query"] = "请联系手机号 13800138000 查询订单"
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = log_observability.build_rag_shadow_log_observability_report(
        input_path=input_path,
        db_path=tmp_path / "bot.db",
    )

    assert report["status"] == "failed"
    assert report["shadow_log_ready"] is False
    assert report["assertions"]["records.no_obvious_sensitive_patterns"] is False
    assert "redact_shadow_log_query_sensitive_patterns" in report["missing_actions"]
    assert "13800138000" not in json.dumps(report, ensure_ascii=False)


def test_invalid_json_returns_structured_failure(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text("{broken-json", encoding="utf-8")

    report = log_observability.build_rag_shadow_log_observability_report(
        input_path=input_path,
        db_path=tmp_path / "bot.db",
    )

    assert report["status"] == "failed"
    assert report["shadow_log_ready"] is False
    assert report["assertions"]["records.present"] is False


def test_shadow_log_cli_writes_json(monkeypatch, tmp_path: Path) -> None:
    _patch_shadow_search(monkeypatch)
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "report.json"
    db_path = tmp_path / "bot.db"
    db_path.write_text("", encoding="utf-8")
    input_path.write_text(
        json.dumps(_input_payload(), ensure_ascii=False), encoding="utf-8"
    )

    exit_code = log_observability.main(
        [
            "--input",
            str(input_path),
            "--db",
            str(db_path),
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["shadow_log_ready"] is True
