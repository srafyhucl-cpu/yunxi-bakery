"""真实脱敏会话 replay 接入准备度测试。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import check_real_conversation_replay_intake_readiness as readiness


def test_intake_readiness_passes_for_default_synthetic_contract_pool() -> None:
    report = readiness.build_real_replay_intake_readiness_report()

    assert report["status"] == "passed"
    assert report["real_sample_ready"] is False
    assert report["pool"]["synthetic_entries"] == 1
    assert (
        "collect_real_customer_conversations_outside_repo" in report["missing_actions"]
    )
    assert report["boundaries"]["real_customer_data_committed"] is False
    artifact_paths = [item["path"] for item in report["artifacts"]]
    assert "scripts/build_real_conversation_replay_intake_packet.py" in artifact_paths


def test_intake_readiness_require_real_fails_without_real_pool() -> None:
    report = readiness.build_real_replay_intake_readiness_report(require_real=True)

    assert report["status"] == "failed"
    assert report["real_sample_ready"] is False
    assert report["failed"] >= 1


def test_intake_readiness_passes_with_approved_real_pool(tmp_path: Path) -> None:
    manifest_path = tmp_path / "pool.json"
    fixture_path = tmp_path / "real-redacted.json"
    write_real_redacted_fixture(fixture_path)
    write_real_manifest(manifest_path, fixture_path)

    report = readiness.build_real_replay_intake_readiness_report(
        manifest_path=manifest_path,
        require_real=True,
    )

    assert report["status"] == "passed"
    assert report["real_sample_ready"] is True
    assert report["pool"]["real_entries"] == 1
    assert report["missing_actions"] == []


def test_intake_readiness_cli_writes_json(tmp_path: Path) -> None:
    output_path = tmp_path / "intake.json"

    exit_code = readiness.main(
        [
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["real_sample_ready"] is False


def write_real_redacted_fixture(fixture_path: Path) -> None:
    payload = json.loads(
        Path("tests/fixtures/customer_real_replay_coverage_sample.json").read_text(
            encoding="utf-8"
        )
    )
    payload["metadata"]["source"] = "unit_test_real_redacted_intake"
    payload["metadata"]["redaction"] = "manual_redaction_v1"
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_real_manifest(manifest_path: Path, fixture_path: Path) -> None:
    manifest_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "source": "unit_test_real_pool",
                    "contains_real_customer_data": True,
                },
                "entries": [
                    {
                        "name": "approved_real_pool",
                        "fixture": str(fixture_path),
                        "enabled": True,
                        "is_real_customer_data": True,
                        "purpose": "approved_redacted_regression",
                        "source_type": "real_customer_conversation",
                        "redaction_method": "manual_redaction_v1",
                        "redaction_reviewer": "qa-owner",
                        "redaction_reviewed_at": "2026-07-10",
                        "raw_source_retention": "not_committed",
                        "min_per_scenario": 5,
                        "evidence_id": "E-UNIT-REAL",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
