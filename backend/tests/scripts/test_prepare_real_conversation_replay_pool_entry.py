"""真实脱敏 replay 样本池条目草稿测试。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import prepare_real_conversation_replay_pool_entry as prepare_entry


def test_prepare_pool_entry_draft_passes_for_reviewed_real_fixture(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "real-redacted.json"
    write_real_redacted_fixture(fixture_path)

    report = prepare_entry.build_pool_entry_draft_report(
        fixture_path=fixture_path,
        name="approved-real-sample",
        evidence_id="E-UNIT-REAL",
        redaction_method="manual_redaction_v1",
        redaction_reviewer="qa-owner",
        redaction_reviewed_at="2026-07-10",
    )

    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert report["coverage"]["status"] == "passed"
    assert report["entry"]["is_real_customer_data"] is True
    assert report["entry"]["raw_source_retention"] == "not_committed"
    assert report["boundaries"]["manifest_modified"] is False


def test_prepare_pool_entry_draft_rejects_synthetic_fixture() -> None:
    report = prepare_entry.build_pool_entry_draft_report(
        fixture_path=Path("tests/fixtures/customer_real_replay_coverage_sample.json"),
        name="synthetic-sample",
        evidence_id="E-UNIT-SYNTHETIC",
        redaction_method="manual_redaction_v1",
        redaction_reviewer="qa-owner",
        redaction_reviewed_at="2026-07-10",
    )

    assert report["status"] == "failed"
    assert report["assertions"]["fixture.source_not_synthetic"] is False


def test_prepare_pool_entry_draft_requires_review_fields(tmp_path: Path) -> None:
    fixture_path = tmp_path / "real-redacted.json"
    write_real_redacted_fixture(fixture_path)

    report = prepare_entry.build_pool_entry_draft_report(
        fixture_path=fixture_path,
        name="approved-real-sample",
        evidence_id="",
        redaction_method="",
        redaction_reviewer="",
        redaction_reviewed_at="",
    )

    assert report["status"] == "failed"
    assert report["assertions"]["evidence_id.present"] is False
    assert report["assertions"]["redaction_method.present"] is False
    assert report["assertions"]["redaction_reviewer.present"] is False
    assert report["assertions"]["redaction_reviewed_at.present"] is False


def test_prepare_pool_entry_draft_cli_writes_json(tmp_path: Path) -> None:
    fixture_path = tmp_path / "real-redacted.json"
    output_path = tmp_path / "entry.json"
    write_real_redacted_fixture(fixture_path)

    exit_code = prepare_entry.main(
        [
            "--fixture",
            str(fixture_path),
            "--name",
            "approved-real-sample",
            "--evidence-id",
            "E-UNIT-REAL",
            "--redaction-method",
            "manual_redaction_v1",
            "--redaction-reviewer",
            "qa-owner",
            "--redaction-reviewed-at",
            "2026-07-10",
            "--source-type",
            "real_customer_conversation",
            "--raw-source-retention",
            "not_committed",
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["entry"]["name"] == "approved-real-sample"
    assert payload["entry"]["source_type"] == "real_customer_conversation"
    assert payload["entry"]["raw_source_retention"] == "not_committed"


def write_real_redacted_fixture(fixture_path: Path) -> None:
    payload = json.loads(
        Path("tests/fixtures/customer_real_replay_coverage_sample.json").read_text(
            encoding="utf-8"
        )
    )
    payload["metadata"]["source"] = "unit_test_real_redacted_entry"
    payload["metadata"]["redaction"] = "manual_redaction_v1"
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
