"""真实脱敏 replay 候选样本审计测试。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_real_conversation_replay_candidate as candidate_audit


def test_missing_fixture_passes_readiness_without_claiming_ready() -> None:
    report = candidate_audit.build_real_replay_candidate_audit_report()

    assert report["status"] == "passed"
    assert report["candidate_ready"] is False
    assert "provide_redacted_real_replay_candidate_fixture" in report["missing_actions"]
    assert report["boundaries"]["real_customer_data_committed"] is False


def test_missing_fixture_fails_when_required() -> None:
    report = candidate_audit.build_real_replay_candidate_audit_report(
        require_fixture=True
    )

    assert report["status"] == "failed"
    assert report["candidate_ready"] is False
    assert report["assertions"]["candidate.fixture_present"] is False


def test_synthetic_fixture_is_rejected_as_real_candidate() -> None:
    report = candidate_audit.build_real_replay_candidate_audit_report(
        fixture_path=Path("tests/fixtures/customer_real_replay_coverage_sample.json"),
        source_type="real_customer_conversation",
        redaction_method="manual_redaction_v1",
        redaction_reviewer="qa-owner",
        redaction_reviewed_at="2026-07-10",
        raw_source_retention="not_committed",
        evidence_id="E-UNIT-CANDIDATE",
    )

    assert report["status"] == "failed"
    assert report["candidate_ready"] is False
    assert report["assertions"]["fixture.source_not_synthetic"] is False
    assert "provide_non_synthetic_real_candidate_source" in report["missing_actions"]


def test_candidate_rejects_privacy_pattern(tmp_path: Path) -> None:
    fixture_path = tmp_path / "candidate.json"
    write_candidate_fixture(fixture_path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["cases"][0]["user_message"] = "请帮我查手机号 13800138000 的订单"
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = candidate_audit.build_real_replay_candidate_audit_report(
        fixture_path=fixture_path,
        source_type="real_customer_conversation",
        redaction_method="manual_redaction_v1",
        redaction_reviewer="qa-owner",
        redaction_reviewed_at="2026-07-10",
        raw_source_retention="not_committed",
        evidence_id="E-UNIT-CANDIDATE",
    )

    assert report["status"] == "failed"
    assert report["assertions"]["replay.passed"] is False
    assert "fix_candidate_replay_contract_failures" in report["missing_actions"]


def test_valid_candidate_emits_manifest_entry_draft(tmp_path: Path) -> None:
    fixture_path = tmp_path / "candidate.json"
    write_candidate_fixture(fixture_path)

    report = candidate_audit.build_real_replay_candidate_audit_report(
        fixture_path=fixture_path,
        name="approved_real_candidate",
        source_type="real_customer_conversation",
        redaction_method="manual_redaction_v1",
        redaction_reviewer="qa-owner",
        redaction_reviewed_at="2026-07-10",
        raw_source_retention="not_committed",
        evidence_id="E-UNIT-CANDIDATE",
    )

    assert report["status"] == "passed"
    assert report["candidate_ready"] is True
    assert report["coverage"]["status"] == "passed"
    assert report["manifest_entry_draft"]["name"] == "approved_real_candidate"
    assert report["manifest_entry_draft"]["is_real_customer_data"] is True
    assert report["boundaries"]["manifest_modified"] is False


def test_cli_writes_json(tmp_path: Path) -> None:
    fixture_path = tmp_path / "candidate.json"
    output_path = tmp_path / "report.json"
    write_candidate_fixture(fixture_path)

    exit_code = candidate_audit.main(
        [
            "--fixture",
            str(fixture_path),
            "--source-type",
            "real_customer_conversation",
            "--redaction-method",
            "manual_redaction_v1",
            "--redaction-reviewer",
            "qa-owner",
            "--redaction-reviewed-at",
            "2026-07-10",
            "--raw-source-retention",
            "not_committed",
            "--evidence-id",
            "E-UNIT-CANDIDATE",
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["candidate_ready"] is True


def write_candidate_fixture(fixture_path: Path) -> None:
    payload = json.loads(
        Path("tests/fixtures/customer_real_replay_coverage_sample.json").read_text(
            encoding="utf-8"
        )
    )
    payload["metadata"]["source"] = "unit_test_real_redacted_candidate"
    payload["metadata"]["redaction"] = "manual_redaction_v1"
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
