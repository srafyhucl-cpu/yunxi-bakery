"""LangChain 作品集证据清单测试。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import build_langchain_portfolio_evidence_packet as portfolio_packet


def test_missing_reports_pass_readiness_without_claiming_verified(
    tmp_path: Path,
) -> None:
    paths = build_paths(tmp_path)
    report = portfolio_packet.build_portfolio_evidence_packet(
        paths=paths,
        release_packet=build_release_packet(),
    )

    assert report["status"] == "passed"
    assert report["verified_evidence_ready"] is False
    assert report["external_evidence_complete"] is False
    assert report["portfolio_complete"] is False
    assert "refresh_current_version_agent_eval" in report["missing_actions"]
    assert (
        report["boundaries"]["missing_external_evidence_treated_as_complete"] is False
    )


def test_verified_engineering_evidence_does_not_complete_external_stages(
    tmp_path: Path,
) -> None:
    paths = build_paths(tmp_path)
    write_verified_reports(paths)

    report = portfolio_packet.build_portfolio_evidence_packet(
        paths=paths,
        require_verified_evidence=True,
        release_packet=build_release_packet(),
    )

    assert report["status"] == "passed"
    assert report["verified_evidence_ready"] is True
    assert report["external_evidence_complete"] is False
    assert report["portfolio_complete"] is False
    assert report["stage_readiness"]["E1_real_replay"]["ready"] is False
    assert report["stage_readiness"]["E4_langsmith_production_export"]["ready"] is False


def test_require_verified_evidence_fails_when_reports_are_missing(
    tmp_path: Path,
) -> None:
    report = portfolio_packet.build_portfolio_evidence_packet(
        paths=build_paths(tmp_path),
        require_verified_evidence=True,
        release_packet=build_release_packet(),
    )

    assert report["status"] == "failed"
    assert report["failed"] == 1


def test_require_complete_passes_only_with_all_stage_evidence(
    tmp_path: Path,
) -> None:
    paths = build_paths(tmp_path)
    write_verified_reports(paths, external_complete=True)

    report = portfolio_packet.build_portfolio_evidence_packet(
        paths=paths,
        require_complete=True,
        release_packet=build_release_packet(external_complete=True),
    )

    assert report["status"] == "passed"
    assert report["verified_evidence_ready"] is True
    assert report["external_evidence_complete"] is True
    assert report["portfolio_complete"] is True


def test_langsmith_enabled_without_export_verification_does_not_complete_e4(
    tmp_path: Path,
) -> None:
    paths = build_paths(tmp_path)
    write_verified_reports(paths, external_complete=True)
    write_json(
        paths.langsmith_production_export,
        {
            "status": "passed",
            "app_version": portfolio_packet.APP_VERSION,
            "enabled": True,
            "external_export_approved": False,
            "external_trace_verified": False,
            "sample_rate": 0.05,
        },
    )

    report = portfolio_packet.build_portfolio_evidence_packet(
        paths=paths,
        require_complete=True,
        release_packet=build_release_packet(external_complete=True),
    )

    assert report["status"] == "failed"
    assert report["stage_readiness"]["E4_langsmith_production_export"]["ready"] is False
    assert report["portfolio_complete"] is False


def test_synthetic_coverage_report_does_not_complete_e5(tmp_path: Path) -> None:
    paths = build_paths(tmp_path)
    write_verified_reports(paths, external_complete=True)
    write_json(
        paths.real_replay_coverage,
        {
            "status": "passed",
            "failed": 0,
            "fixture": "tests/fixtures/customer_real_replay_coverage_sample.json",
        },
    )

    report = portfolio_packet.build_portfolio_evidence_packet(
        paths=paths,
        require_complete=True,
        release_packet=build_release_packet(external_complete=True),
    )

    assert report["status"] == "failed"
    assert (
        report["stage_readiness"]["E5_real_fact_sensitive_coverage"]["ready"] is False
    )
    assert report["portfolio_complete"] is False


def test_cli_writes_current_workspace_summary(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "portfolio.json"

    exit_code = portfolio_packet.main(["--json-out", str(output_path), "--summary"])
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert (
        "langchain_portfolio_evidence_packet status=passed" in capsys.readouterr().out
    )


def build_paths(tmp_path: Path) -> portfolio_packet.PortfolioEvidencePaths:
    return portfolio_packet.PortfolioEvidencePaths(
        agent_eval=tmp_path / "agent-eval.json",
        rag_shadow=tmp_path / "rag-shadow.json",
        rag_shadow_log=tmp_path / "rag-shadow-log.json",
        rag_gray_release=tmp_path / "rag-gray-release.json",
        langsmith_production_export=tmp_path / "langsmith-export.json",
        observability=tmp_path / "observability.json",
        real_replay_coverage=tmp_path / "real-replay-coverage.json",
        release_report=tmp_path / "release.json",
    )


def write_verified_reports(
    paths: portfolio_packet.PortfolioEvidencePaths,
    *,
    external_complete: bool = False,
) -> None:
    write_json(
        paths.agent_eval,
        {
            "status": "passed",
            "total": 133,
            "failed": 0,
            "pass_rate": 1.0,
            "metadata": {"app_version": portfolio_packet.APP_VERSION},
        },
    )
    write_json(
        paths.rag_shadow,
        {"status": "passed", "failed": 0, "baseline": {}, "candidates": []},
    )
    write_json(
        paths.rag_shadow_log,
        {"status": "passed", "shadow_log_ready": external_complete},
    )
    write_json(
        paths.rag_gray_release,
        {
            "status": "passed",
            "app_version": portfolio_packet.APP_VERSION,
            "gray_release_verified": external_complete,
            "configured_mode": "planned-hybrid" if external_complete else "hybrid",
            "release_evidence_packet_ready": external_complete,
        },
    )
    write_json(
        paths.langsmith_production_export,
        {
            "status": "passed",
            "app_version": portfolio_packet.APP_VERSION,
            "enabled": external_complete,
            "external_export_approved": external_complete,
            "external_trace_verified": external_complete,
            "sample_rate": 0.05 if external_complete else 0.0,
        },
    )
    write_json(
        paths.observability,
        {
            "status": "passed",
            "failed": 0,
            "trace": {"status": "ok", "total_runs": 2},
            "langsmith": {"enabled": external_complete},
        },
    )
    write_json(
        paths.real_replay_coverage,
        {"status": "passed", "failed": 0, "fixture": "redacted-real.json"},
    )


def build_release_packet(*, external_complete: bool = False) -> dict[str, object]:
    return {
        "status": "passed",
        "app_version": portfolio_packet.APP_VERSION,
        "packet_ready": True,
        "real_replay": {
            "candidate_audit": {"candidate_ready": external_complete},
            "intake_readiness": {"real_sample_ready": external_complete},
        },
        "langsmith": {"enabled": external_complete},
        "rag": {"configured_mode": "hybrid"},
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
