from __future__ import annotations

import json
from pathlib import Path

from scripts import build_rag_shadow_log_intake_packet as intake_packet
from scripts import report_rag_shadow_log_observability as log_observability


class _FakeSearcher:
    def __init__(self, keys: list[str]) -> None:
        self._keys = keys

    def search(self, query: str, limit: int) -> list[tuple[str, float]]:
        return [(key, 1.0) for key in self._keys[:limit]]


def test_intake_packet_contains_handoff_contract_and_command_chain() -> None:
    report = intake_packet.build_rag_shadow_log_intake_packet(
        operator="reviewer_a",
        evidence_id="E-RAG-SHADOW-001",
    )

    assert report["status"] == "passed"
    assert report["readiness"]["shadow_log_ready"] is False
    assert report["boundaries"]["missing_external_input_treated_as_ready"] is False
    assert report["boundaries"]["readiness_changed"] is False
    metadata = report["handoff_template"]["metadata"]
    assert metadata["source_type"] == "real_customer_rag_shadow_log"
    assert metadata["contains_sensitive_data"] is False
    assert metadata["raw_source_retention"] == "not_committed"
    assert metadata["redaction_reviewer"] == "reviewer_a"
    assert metadata["evidence_id"] == "E-RAG-SHADOW-001"
    assert set(report["required_record_fields"]) == {
        "id",
        "query",
        "baseline_top_keys",
    }
    assert [command["step"] for command in report["commands"]] == [
        "validate_redacted_shadow_log",
        "refresh_portfolio_evidence",
        "verify_production_plan",
    ]
    assert "--require-input" in report["commands"][0]["command"]
    checklist_ids = {item["id"] for item in report["pre_submission_checklist"]}
    assert checklist_ids == {
        "source_is_real_rag_shadow_log",
        "raw_shadow_log_kept_outside_repo",
        "query_text_redacted",
        "metadata_proof_fields_present",
        "evidence_id_registered",
    }
    assert all(item["owner"] for item in report["pre_submission_checklist"])
    assert all(
        item["human_input_required"] is True
        for item in report["pre_submission_checklist"]
    )


def test_filled_handoff_template_passes_strict_input_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    patch_shadow_search(monkeypatch)
    packet = intake_packet.build_rag_shadow_log_intake_packet()
    handoff = packet["handoff_template"]
    handoff["metadata"].update(
        {
            "redaction_method": "tool_redaction_plus_manual_review",
            "redaction_reviewer": "reviewer_b",
            "redaction_reviewed_at": "2026-07-10",
            "evidence_id": "E-RAG-SHADOW-002",
        }
    )
    handoff["records"][0].update(
        {
            "id": "rag-shadow-redacted-001",
            "group": "inventory",
            "query": "脱敏库存咨询",
            "baseline_top_keys": ["kb_1", "kb_2"],
        }
    )
    input_path = tmp_path / "rag-shadow-input.json"
    input_path.write_text(json.dumps(handoff, ensure_ascii=False), encoding="utf-8")

    report = log_observability.build_rag_shadow_log_observability_report(
        input_path=input_path,
        db_path=tmp_path / "bot.db",
        require_input=True,
    )

    assert report["status"] == "passed"
    assert report["shadow_log_ready"] is True
    assert report["metadata"]["evidence_id"] == "E-RAG-SHADOW-002"
    assert "query" not in report["records"][0]


def test_intake_packet_rejects_invalid_recommended_record_count() -> None:
    report = intake_packet.build_rag_shadow_log_intake_packet(
        recommended_record_count=0
    )

    assert report["status"] == "failed"
    assert report["assertions"]["recommended_record_count.positive"] is False


def test_intake_packet_cli_writes_json(tmp_path: Path) -> None:
    output_path = tmp_path / "packet.json"

    exit_code = intake_packet.main(
        [
            "--operator",
            "reviewer_c",
            "--evidence-id",
            "E-RAG-SHADOW-003",
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["operator"] == "reviewer_c"
    assert payload["evidence_id"] == "E-RAG-SHADOW-003"
    assert payload["readiness"]["shadow_log_ready"] is False


def patch_shadow_search(monkeypatch) -> None:
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
        if scenario.name in {"hybrid", "planned-hybrid"}:
            return _FakeSearcher(["kb_1", "kb_2"])
        return _FakeSearcher(["kb_9", "kb_2"])

    monkeypatch.setattr(
        log_observability.eval_matrix,
        "build_searcher",
        fake_build_searcher,
    )
