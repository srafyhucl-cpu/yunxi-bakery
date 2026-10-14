"""LangChain 生产观测发布证据门禁测试。"""

from __future__ import annotations

from pathlib import Path

from scripts import check_langchain_production_observability_release as checker


def test_passes_when_release_report_has_matching_production_evidence(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "release.json"
    report_path.write_text(
        checker.json.dumps(build_release_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    report = checker.build_production_observability_release_report(
        report_path,
        expected_version="0.97.2",
    )

    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert report["production"]["endpoint_versions"] == {
        "健康检查接口": "0.97.2",
        "就绪检查接口": "0.97.2",
    }
    assert report["observability"]["langsmith_enabled"] is False
    assert report["observability"]["langsmith_enabled_explicit"] is True
    assert report["capacity"]["production_runtime_status"] == "ok"
    assert report["capacity"]["service_active"] is True


def test_fails_current_production_drift_shape(tmp_path: Path) -> None:
    report_path = tmp_path / "release.json"
    payload = build_release_payload(
        release_status="failed",
        release_failed=1,
        health_version="0.85.2",
        ready_version="0.85.2",
        callback_status="failed",
        callback_failed=2,
        callback_failed_names=[
            "p2c-today-wait-buyer-confirm-list",
            "p2c-refund-policy-knowledge",
        ],
    )
    report_path.write_text(
        checker.json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    report = checker.build_production_observability_release_report(
        report_path,
        expected_version="0.97.2",
    )
    finding_codes = [finding["code"] for finding in report["findings"]]

    assert report["status"] == "failed"
    assert "release_gate.failed" in finding_codes
    assert "production_callback.failed" in finding_codes
    assert "production_version_mismatch" in finding_codes
    assert report["production"]["callback_failed_names"] == [
        "p2c-today-wait-buyer-confirm-list",
        "p2c-refund-policy-knowledge",
    ]
    assert report["production"]["endpoint_versions"] == {
        "健康检查接口": "0.85.2",
        "就绪检查接口": "0.85.2",
    }


def test_requires_explicit_langsmith_status(tmp_path: Path) -> None:
    report_path = tmp_path / "release.json"
    payload = build_release_payload()
    observability = payload["release_summary"]["langchain_observability_evidence"]
    observability.pop("langsmith_enabled")
    report_path.write_text(
        checker.json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    report = checker.build_production_observability_release_report(
        report_path,
        expected_version="0.97.2",
    )
    finding_codes = [finding["code"] for finding in report["findings"]]

    assert report["status"] == "failed"
    assert "langsmith_status.missing" in finding_codes
    assert report["observability"]["langsmith_enabled_explicit"] is False


def test_requires_capacity_evidence(tmp_path: Path) -> None:
    report_path = tmp_path / "release.json"
    payload = build_release_payload()
    payload["release_summary"].pop("langchain_ai_layer_capacity")
    report_path.write_text(
        checker.json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    report = checker.build_production_observability_release_report(
        report_path,
        expected_version="0.97.2",
    )
    finding_codes = [finding["code"] for finding in report["findings"]]

    assert report["status"] == "failed"
    assert "capacity_evidence.missing" in finding_codes
    assert report["capacity"]["production_runtime_status"] == "missing"


def test_rejects_capacity_version_drift(tmp_path: Path) -> None:
    report_path = tmp_path / "release.json"
    payload = build_release_payload()
    capacity = payload["release_summary"]["langchain_ai_layer_capacity"]
    capacity["version"] = "0.0.0"
    capacity["health_version"] = "0.0.0"
    report_path.write_text(
        checker.json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    report = checker.build_production_observability_release_report(
        report_path,
        expected_version="0.97.2",
    )
    finding_codes = [finding["code"] for finding in report["findings"]]

    assert report["status"] == "failed"
    assert "capacity_version_mismatch" in finding_codes


def test_main_writes_json_and_summary(tmp_path: Path, capsys) -> None:
    report_path = tmp_path / "release.json"
    output_path = tmp_path / "checked.json"
    report_path.write_text(
        checker.json.dumps(build_release_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = checker.main(
        [
            "--report",
            str(report_path),
            "--expected-version",
            "0.97.2",
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    assert "langchain_production_observability_release status=passed" in (
        capsys.readouterr().out
    )


def build_release_payload(
    *,
    release_status: str = "passed",
    release_failed: int = 0,
    health_version: str = "0.97.2",
    ready_version: str = "0.97.2",
    callback_status: str = "passed",
    callback_failed: int = 0,
    callback_failed_names: list[str] | None = None,
) -> dict[str, object]:
    return {
        "status": release_status,
        "failed": release_failed,
        "release_summary": {
            "production_smoke": {
                "status": "passed",
                "failed": 0,
                "app_version": "0.97.2",
                "failed_names": [],
                "checks": [
                    {
                        "name": "服务端口可达性",
                        "passed": True,
                        "detail": "https://yunxifood.cn:443",
                    },
                    {
                        "name": "健康检查接口",
                        "passed": True,
                        "detail": str({"status": "ok", "version": health_version}),
                    },
                    {
                        "name": "就绪检查接口",
                        "passed": True,
                        "detail": str(
                            {
                                "status": "ready",
                                "version": ready_version,
                                "checks": {"database_schema_ready": True},
                            }
                        ),
                    },
                ],
            },
            "production_employee_callback_probe": {
                "status": callback_status,
                "failed": callback_failed,
                "app_version": "0.97.2",
                "failed_names": callback_failed_names or [],
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
                "trace_latency_ms": 2500.0,
                "payload_bytes": 2227,
                "production_runtime_status": "ok",
                "service_active": True,
                "version": health_version,
                "health_version": health_version,
                "ready_version": ready_version,
                "rss_mb": 80.0,
                "mem_available_mb": 512.0,
                "load1": 0.2,
            },
        },
    }
