"""LangChain 生产同步交接报告测试。"""

from __future__ import annotations

from pathlib import Path

from scripts import report_langchain_production_sync_handoff as handoff


def test_handoff_blocks_on_release_failure_and_ssh_denied(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        handoff.release_check, "read_expected_version", lambda: "0.98.0"
    )
    release_report_path = tmp_path / "release.json"
    release_report_path.write_text(
        handoff.json.dumps(
            build_release_payload(
                release_status="failed",
                health_version="0.85.2",
                ready_version="0.85.2",
                callback_status="failed",
                callback_failed=2,
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = handoff.build_production_sync_handoff_report(
        release_report_path=release_report_path,
        local_commit="abc123",
        remote_refs=(
            handoff.GitRefStatus("origin", "abc123", "ok"),
            handoff.GitRefStatus("server", "abc123", "ok"),
        ),
        runtime_report=build_runtime_report(status="failed"),
        ssh_status="permission_denied",
        ssh_detail="Permission denied",
    )
    blocker_codes = [blocker["code"] for blocker in report["blockers"]]

    assert report["status"] == "blocked"
    assert "production_release_not_ready" in blocker_codes
    assert "production_runtime_version_mismatch" in blocker_codes
    assert "server_ssh_unavailable" in blocker_codes
    assert report["release_check"]["production"]["callback_failed"] == 2
    assert report["manual_actions"][0] == "用具备生产权限的账号登录服务器。"


def test_handoff_blocks_on_remote_ref_mismatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        handoff.release_check, "read_expected_version", lambda: "0.98.0"
    )
    release_report_path = tmp_path / "release.json"
    release_report_path.write_text(
        handoff.json.dumps(build_release_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    report = handoff.build_production_sync_handoff_report(
        release_report_path=release_report_path,
        local_commit="target",
        remote_refs=(
            handoff.GitRefStatus("origin", "target", "ok"),
            handoff.GitRefStatus("server", "old", "ok"),
        ),
        runtime_report=build_runtime_report(),
        ssh_status="available",
    )
    blocker_codes = [blocker["code"] for blocker in report["blockers"]]

    assert report["status"] == "blocked"
    assert blocker_codes == ["remote_ref_mismatch"]
    assert report["blockers"][0]["detail"]["remote"] == "server"


def test_handoff_passes_when_release_refs_and_ssh_are_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        handoff.release_check, "read_expected_version", lambda: "0.98.0"
    )
    release_report_path = tmp_path / "release.json"
    release_report_path.write_text(
        handoff.json.dumps(build_release_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    report = handoff.build_production_sync_handoff_report(
        release_report_path=release_report_path,
        local_commit="target",
        remote_refs=(
            handoff.GitRefStatus("origin", "target", "ok"),
            handoff.GitRefStatus("server", "target", "ok"),
        ),
        runtime_report=build_runtime_report(),
        ssh_status="available",
    )

    assert report["status"] == "passed"
    assert report["blockers"] == []
    assert report["post_sync_verification"][-1] == (
        "python scripts\\check_evidence_index.py --summary"
    )
    assert report["post_sync_verification"][0] == (
        "python scripts\\check_langchain_production_runtime_version.py --summary"
    )
    assert report["post_sync_verification"][3] == (
        "python scripts\\report_langchain_production_callback_failures.py "
        "--json-out reports\\harness\\langchain-production-callback-failures-latest.json "
        "--summary"
    )


def test_main_writes_json_and_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        handoff.release_check, "read_expected_version", lambda: "0.98.0"
    )
    monkeypatch.setattr(handoff, "read_local_commit", lambda: "target")
    monkeypatch.setattr(
        handoff,
        "asyncio_run_runtime_check",
        lambda _expected_version: build_runtime_report(),
    )
    monkeypatch.setattr(
        handoff,
        "read_remote_ref",
        lambda name: handoff.GitRefStatus(name, "target", "ok"),
    )
    release_report_path = tmp_path / "release.json"
    output_path = tmp_path / "handoff.json"
    release_report_path.write_text(
        handoff.json.dumps(build_release_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = handoff.main(
        [
            "--release-report",
            str(release_report_path),
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    assert "langchain_production_sync_handoff status=passed" in (
        capsys.readouterr().out
    )


def build_release_payload(
    *,
    release_status: str = "passed",
    health_version: str = "0.98.0",
    ready_version: str = "0.98.0",
    callback_status: str = "passed",
    callback_failed: int = 0,
) -> dict[str, object]:
    return {
        "status": release_status,
        "failed": 0 if release_status == "passed" else 1,
        "release_summary": {
            "production_smoke": {
                "status": "passed",
                "failed": 0,
                "app_version": "0.98.0",
                "failed_names": [],
                "checks": [
                    {
                        "name": "健康检查接口",
                        "passed": True,
                        "detail": str({"status": "ok", "version": health_version}),
                    },
                    {
                        "name": "就绪检查接口",
                        "passed": True,
                        "detail": str({"status": "ready", "version": ready_version}),
                    },
                ],
            },
            "production_employee_callback_probe": {
                "status": callback_status,
                "failed": callback_failed,
                "failed_names": [
                    "p2c-today-wait-buyer-confirm-list",
                    "p2c-refund-policy-knowledge",
                ]
                if callback_failed
                else [],
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
                "version": "0.98.0",
                "health_version": "0.98.0",
                "ready_version": "0.98.0",
            },
        },
    }


def build_runtime_report(status: str = "passed") -> dict[str, object]:
    is_passed = status == "passed"
    version = "0.99.0" if is_passed else "0.85.2"
    return {
        "status": status,
        "expected_version": "0.99.0",
        "endpoint_versions": {"health": version, "ready": version},
        "failed": 0 if is_passed else 2,
        "failed_names": [] if is_passed else ["health", "ready"],
    }
