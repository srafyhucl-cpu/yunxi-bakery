from __future__ import annotations

import json
from pathlib import Path

from scripts import check_langsmith_production_rollout as rollout


def test_rollout_default_disabled_plan_passes_without_external_export() -> None:
    report = rollout.build_langsmith_production_rollout_report()

    assert report["status"] == "passed"
    assert report["rollout"]["enabled"] is False
    assert report["rollout"]["sample_rate"] == 0.0
    assert report["boundaries"]["production_env_changed"] is False
    assert report["boundaries"]["langsmith_external_export"] is False
    assert report["missing_actions"] == []


def test_rollout_rejects_unsafe_sample_rate() -> None:
    report = rollout.build_langsmith_production_rollout_report(sample_rate=0.5)

    assert report["status"] == "failed"
    assert report["assertions"]["sample_rate.within_safe_default"] is False
    assert "lower_langsmith_sample_rate_to_safe_default" in report["missing_actions"]


def test_rollout_require_enabled_needs_runtime_and_compliance(monkeypatch) -> None:
    monkeypatch.setattr(
        rollout,
        "build_langsmith_runtime_config_report",
        lambda require_enabled: {
            "status": "passed",
            "runtime": {
                "enabled": True,
                "safe_to_enable": True,
                "project": "prod",
                "api_key_configured": True,
                "missing": [],
            },
            "metadata_redaction": {"status": "passed"},
        },
    )

    report = rollout.build_langsmith_production_rollout_report(
        sample_rate=0.05,
        require_enabled=True,
        external_export_approved=False,
    )

    assert report["status"] == "failed"
    assert report["assertions"]["runtime_config.safe_to_enable"] is True
    assert report["assertions"]["external_export.approved"] is False


def test_rollout_require_enabled_passes_when_runtime_and_compliance_ready(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        rollout,
        "build_langsmith_runtime_config_report",
        lambda require_enabled: {
            "status": "passed",
            "runtime": {
                "enabled": True,
                "safe_to_enable": True,
                "project": "prod",
                "api_key_configured": True,
                "missing": [],
            },
            "metadata_redaction": {"status": "passed"},
        },
    )

    report = rollout.build_langsmith_production_rollout_report(
        sample_rate=0.05,
        require_enabled=True,
        external_export_approved=True,
    )

    assert report["status"] == "passed"
    assert report["rollout"]["sample_rate"] == 0.05


def test_rollout_cli_writes_json(tmp_path: Path) -> None:
    output_path = tmp_path / "rollout.json"

    exit_code = rollout.main(
        [
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["rollout"]["sample_rate"] == 0.0
