from __future__ import annotations

import json
from pathlib import Path

from scripts import build_langsmith_production_enablement_packet as enablement


def test_enablement_packet_contains_env_commands_and_boundaries() -> None:
    report = enablement.build_langsmith_enablement_packet(
        project="yunxi-prod",
        sample_rate=0.05,
        operator="ops_a",
        evidence_id="E-LS-001",
    )

    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert report["boundaries"]["production_env_changed"] is False
    assert report["boundaries"]["langsmith_external_export"] is False
    assert report["boundaries"]["api_key_printed"] is False
    assert report["boundaries"]["business_database_read"] is False

    env_names = {item["name"] for item in report["required_env_vars"]}
    assert env_names == {
        "LANGCHAIN_TRACING_ENABLED",
        "LANGCHAIN_TRACING_V2",
        "LANGSMITH_TRACING",
        "LANGCHAIN_PROJECT",
        "LANGSMITH_API_KEY",
    }
    assert all(
        "sk-" not in str(item["expected"]) for item in report["required_env_vars"]
    )
    assert (
        "LANGSMITH_API_KEY=<configured outside repo>"
        in report["commands"]["enable_env"]
    )
    assert "systemctl restart yunxibakebot" in report["commands"]["rollback"]


def test_enablement_packet_rejects_zero_or_unsafe_sample_rate() -> None:
    zero_report = enablement.build_langsmith_enablement_packet(sample_rate=0.0)
    high_report = enablement.build_langsmith_enablement_packet(sample_rate=0.5)

    assert zero_report["status"] == "failed"
    assert zero_report["assertions"]["sample_rate.within_safe_default"] is False
    assert high_report["status"] == "failed"
    assert high_report["assertions"]["sample_rate.within_safe_default"] is False


def test_enablement_packet_rejects_missing_project_operator_or_evidence() -> None:
    report = enablement.build_langsmith_enablement_packet(
        project="",
        operator="",
        evidence_id="",
    )

    assert report["status"] == "failed"
    assert report["assertions"]["project.present"] is False
    assert report["assertions"]["operator.present"] is False
    assert report["assertions"]["evidence_id.present"] is False


def test_enablement_packet_uses_custom_sample_rate_in_commands() -> None:
    report = enablement.build_langsmith_enablement_packet(sample_rate=0.03)

    assert report["status"] == "passed"
    assert "--sample-rate 0.03" in report["next_gate"]
    assert any(
        "--sample-rate 0.03" in command for command in report["commands"]["pre_enable"]
    )


def test_enablement_packet_cli_writes_json(tmp_path: Path) -> None:
    output_path = tmp_path / "enablement.json"

    exit_code = enablement.main(
        [
            "--project",
            "yunxi-prod",
            "--sample-rate",
            "0.05",
            "--operator",
            "ops_b",
            "--evidence-id",
            "E-LS-002",
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["project"] == "yunxi-prod"
    assert payload["operator"] == "ops_b"
    assert payload["evidence_id"] == "E-LS-002"
