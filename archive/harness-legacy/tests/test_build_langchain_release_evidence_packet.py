"""LangChain 发布证据包测试。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import build_langchain_release_evidence_packet as evidence_packet


def test_missing_release_report_passes_readiness_without_claiming_ready(
    tmp_path: Path,
) -> None:
    report = evidence_packet.build_release_evidence_packet(
        release_report_path=tmp_path / "missing.json"
    )

    assert report["status"] == "passed"
    assert report["packet_ready"] is False
    assert (
        "run_langchain_release_gate_with_production_evidence"
        in report["missing_actions"]
    )
    assert report["boundaries"]["business_database_read"] is False


def test_missing_release_report_fails_when_required(tmp_path: Path) -> None:
    report = evidence_packet.build_release_evidence_packet(
        release_report_path=tmp_path / "missing.json",
        require_production_evidence=True,
    )

    assert report["status"] == "failed"
    assert report["packet_ready"] is False
    assert (
        report["assertions"]["require_production_evidence.release_report_present"]
        is False
    )


def test_valid_release_report_builds_ready_packet(tmp_path: Path) -> None:
    report_path = tmp_path / "release.json"
    report_path.write_text(
        json.dumps(build_release_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    report = evidence_packet.build_release_evidence_packet(
        release_report_path=report_path,
        require_production_evidence=True,
        production_commit="abc123",
        production_version=evidence_packet.APP_VERSION,
        production_service_status="active",
    )

    assert report["status"] == "passed"
    assert report["packet_ready"] is True
    assert report["release_gate"]["status"] == "passed"
    assert report["production_observability_release"]["status"] == "passed"
    assert report["production_observability_release"]["callback_failed"] == 0
    assert report["git"]["production_commit"] == "abc123"
    assert report["real_replay"]["candidate_audit"]["candidate_ready"] is False
    assert report["real_replay"]["intake_readiness"]["real_sample_ready"] is False


def test_failed_release_report_blocks_packet(tmp_path: Path) -> None:
    report_path = tmp_path / "release.json"
    payload = build_release_payload(release_status="failed", release_failed=1)
    report_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = evidence_packet.build_release_evidence_packet(
        release_report_path=report_path,
        require_production_evidence=True,
    )

    assert report["status"] == "failed"
    assert report["packet_ready"] is False
    assert report["assertions"]["release_gate.passed"] is False
    assert "fix_failed_release_gate_steps" in report["missing_actions"]


def test_cli_writes_json_summary(tmp_path: Path, capsys) -> None:
    report_path = tmp_path / "release.json"
    output_path = tmp_path / "packet.json"
    report_path.write_text(
        json.dumps(build_release_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = evidence_packet.main(
        [
            "--release-report",
            str(report_path),
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["packet_ready"] is True
    assert "langchain_release_evidence_packet status=passed" in capsys.readouterr().out


def build_release_payload(
    *,
    release_status: str = "passed",
    release_failed: int = 0,
) -> dict[str, object]:
    return {
        "status": release_status,
        "total": 8,
        "failed": release_failed,
        "release_summary": {
            "agent_eval_default": {
                "status": "passed",
                "total": 133,
                "failed": 0,
                "pass_rate": 1.0,
            },
            "agent_eval_with_reply_replay": {
                "status": "passed",
                "total": 163,
                "failed": 0,
                "pass_rate": 1.0,
            },
            "production_smoke": {
                "status": "passed",
                "failed": 0,
                "app_version": evidence_packet.APP_VERSION,
                "checks": [
                    {
                        "name": "健康检查接口",
                        "passed": True,
                        "detail": str(
                            {"status": "ok", "version": evidence_packet.APP_VERSION}
                        ),
                    },
                    {
                        "name": "就绪检查接口",
                        "passed": True,
                        "detail": str(
                            {
                                "status": "ready",
                                "version": evidence_packet.APP_VERSION,
                            }
                        ),
                    },
                ],
            },
            "production_employee_callback_probe": {
                "status": "passed",
                "failed": 0,
                "app_version": evidence_packet.APP_VERSION,
                "failed_names": [],
            },
            "langsmith_runtime_config": {
                "enabled": False,
                "safe_to_enable": False,
                "project": "yunxi-bakebot",
                "api_key_configured": False,
            },
            "langchain_observability_evidence": {
                "status": "passed",
                "failed": 0,
                "trace_status": "ok",
                "trace_total_runs": 2,
                "langsmith_enabled": False,
            },
            "langchain_ai_layer_capacity": {
                "status": "passed",
                "failed": 0,
                "production_runtime_status": "ok",
                "service_active": True,
                "version": evidence_packet.APP_VERSION,
                "health_version": evidence_packet.APP_VERSION,
                "ready_version": evidence_packet.APP_VERSION,
            },
        },
    }
