"""生成 LangChain AI 应用层作品集证据清单。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from scripts import build_langchain_release_evidence_packet as release_evidence  # noqa: E402

TRACE_ID = "20260709-langchain-ai-layer-production-enhancement"
DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "portfolio" / "langchain-ai-layer-evidence-packet.json"
)
PORTFOLIO_CODE_PATHS = (
    "docs/architecture/langchain-ai-layer-portfolio.md",
    "docs/harness-engineering/adr/0003-langchain-ai-layer-boundary.md",
    "app/service/agents/customer/graph.py",
    "app/service/agents/employee/graph.py",
    "app/service/agents/rag/retriever.py",
    "app/service/agents/tools/customer.py",
    "app/service/agents/tools/employee.py",
    "scripts/report_agent_eval.py",
    "scripts/report_rag_shadow_observability.py",
    "scripts/report_langchain_observability_evidence.py",
    "scripts/build_rag_shadow_log_intake_packet.py",
    "scripts/build_langchain_release_evidence_packet.py",
    "scripts/build_langchain_external_evidence_handoff_packet.py",
)


@dataclass(frozen=True)
class PortfolioEvidencePaths:
    agent_eval: Path = ROOT_DIR / "reports" / "agent-eval" / "latest.json"
    rag_shadow: Path = (
        ROOT_DIR / "reports" / "retrieval-shadow" / "rag-shadow-observability.json"
    )
    rag_shadow_log: Path = (
        ROOT_DIR / "reports" / "retrieval-shadow" / "rag-shadow-log-observability.json"
    )
    rag_gray_release: Path = (
        ROOT_DIR
        / "reports"
        / "retrieval-shadow"
        / "rag-planned-hybrid-gray-release.json"
    )
    langsmith_production_export: Path = (
        ROOT_DIR
        / "reports"
        / "agent-traces"
        / "langsmith-production-export-verification.json"
    )
    observability: Path = (
        ROOT_DIR / "reports" / "agent-traces" / "langchain-observability-evidence.json"
    )
    real_replay_coverage: Path = (
        ROOT_DIR / "reports" / "agent-eval" / "real-conversation-replay-coverage.json"
    )
    release_report: Path = release_evidence.DEFAULT_RELEASE_REPORT_PATH


def build_portfolio_evidence_packet(
    *,
    paths: PortfolioEvidencePaths = PortfolioEvidencePaths(),
    require_verified_evidence: bool = False,
    require_complete: bool = False,
    release_packet: dict[str, object] | None = None,
) -> dict[str, object]:
    reports = load_evidence_reports(paths)
    current_release_packet = release_packet
    if current_release_packet is None:
        current_release_packet = release_evidence.build_release_evidence_packet(
            release_report_path=paths.release_report
        )
    architecture = build_architecture_summary()
    evidence = build_evidence_summaries(reports, paths, current_release_packet)
    stage_readiness = build_stage_readiness(evidence)
    assertions = build_assertions(architecture, evidence)
    verified_evidence_ready = all(assertions.values())
    external_evidence_complete = all(
        bool(stage.get("ready")) for stage in stage_readiness.values()
    )
    portfolio_complete = verified_evidence_ready and external_evidence_complete
    failed = count_failed_assertions(
        verified_evidence_ready=verified_evidence_ready,
        portfolio_complete=portfolio_complete,
        require_verified_evidence=require_verified_evidence,
        require_complete=require_complete,
    )
    return {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": utc_now(),
        "trace_id": TRACE_ID,
        "app_version": APP_VERSION,
        "verified_evidence_ready": verified_evidence_ready,
        "external_evidence_complete": external_evidence_complete,
        "portfolio_complete": portfolio_complete,
        "failed": failed,
        "assertions": assertions,
        "missing_actions": build_missing_actions(assertions, stage_readiness),
        "architecture": architecture,
        "evidence": evidence,
        "stage_readiness": stage_readiness,
        "boundaries": build_boundaries(),
    }


def load_evidence_reports(
    paths: PortfolioEvidencePaths,
) -> dict[str, dict[str, object]]:
    return {
        "agent_eval": read_json_report(paths.agent_eval),
        "rag_shadow": read_json_report(paths.rag_shadow),
        "rag_shadow_log": read_json_report(paths.rag_shadow_log),
        "rag_gray_release": read_json_report(paths.rag_gray_release),
        "langsmith_production_export": read_json_report(
            paths.langsmith_production_export
        ),
        "observability": read_json_report(paths.observability),
        "real_replay_coverage": read_json_report(paths.real_replay_coverage),
    }


def build_evidence_summaries(
    reports: dict[str, dict[str, object]],
    paths: PortfolioEvidencePaths,
    release_packet: dict[str, object],
) -> dict[str, dict[str, object]]:
    return {
        "agent_eval": summarize_agent_eval(reports["agent_eval"], paths.agent_eval),
        "rag_shadow": summarize_rag_shadow(reports["rag_shadow"], paths.rag_shadow),
        "rag_shadow_log": summarize_rag_shadow_log(
            reports["rag_shadow_log"], paths.rag_shadow_log
        ),
        "rag_gray_release": summarize_rag_gray_release(
            reports["rag_gray_release"], paths.rag_gray_release
        ),
        "langsmith_production_export": summarize_langsmith_production_export(
            reports["langsmith_production_export"],
            paths.langsmith_production_export,
        ),
        "observability": summarize_observability(
            reports["observability"], paths.observability
        ),
        "real_replay_coverage": summarize_real_replay_coverage(
            reports["real_replay_coverage"], paths.real_replay_coverage
        ),
        "release": summarize_release_packet(release_packet, paths.release_report),
    }


def build_architecture_summary() -> dict[str, object]:
    checks = [
        {"path": relative_path, "present": (ROOT_DIR / relative_path).is_file()}
        for relative_path in PORTFOLIO_CODE_PATHS
    ]
    return {
        "boundary": "langchain_ai_layer_only",
        "business_domain_owner": "service_repository_models",
        "code_paths": checks,
        "missing_paths": [check["path"] for check in checks if not check["present"]],
    }


def summarize_agent_eval(report: dict[str, object], path: Path) -> dict[str, object]:
    metadata = dict_value(report, "metadata")
    return {
        "path": str(path),
        "present": bool(report),
        "status": report.get("status", "missing"),
        "total": report.get("total", 0),
        "failed": report.get("failed", 0),
        "pass_rate": report.get("pass_rate", 0.0),
        "app_version": metadata.get("app_version", ""),
        "generated_at": metadata.get("generated_at", ""),
    }


def summarize_rag_shadow(report: dict[str, object], path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "present": bool(report),
        "status": report.get("status", "missing"),
        "failed": report.get("failed", 0),
        "baseline": report.get("baseline", {}),
        "candidates": report.get("candidates", []),
    }


def summarize_rag_shadow_log(
    report: dict[str, object], path: Path
) -> dict[str, object]:
    return {
        "path": str(path),
        "present": bool(report),
        "status": report.get("status", "missing"),
        "shadow_log_ready": report.get("shadow_log_ready", False),
        "missing_actions": report.get("missing_actions", []),
    }


def summarize_rag_gray_release(
    report: dict[str, object], path: Path
) -> dict[str, object]:
    is_verified = (
        report.get("status") == "passed"
        and report.get("app_version") == APP_VERSION
        and report.get("gray_release_verified") is True
        and report.get("configured_mode") == "planned-hybrid"
        and report.get("release_evidence_packet_ready") is True
    )
    return {
        "path": str(path),
        "present": bool(report),
        "status": report.get("status", "missing"),
        "gray_release_verified": is_verified,
        "configured_mode": report.get("configured_mode", "hybrid"),
    }


def summarize_langsmith_production_export(
    report: dict[str, object], path: Path
) -> dict[str, object]:
    sample_rate = report.get("sample_rate", 0.0)
    is_safe_sample_rate = (
        isinstance(sample_rate, int | float) and 0.0 < sample_rate <= 0.1
    )
    is_verified = (
        report.get("status") == "passed"
        and report.get("app_version") == APP_VERSION
        and report.get("enabled") is True
        and report.get("external_export_approved") is True
        and report.get("external_trace_verified") is True
        and is_safe_sample_rate
    )
    return {
        "path": str(path),
        "present": bool(report),
        "status": report.get("status", "missing"),
        "external_export_verified": is_verified,
        "sample_rate": sample_rate,
    }


def summarize_observability(report: dict[str, object], path: Path) -> dict[str, object]:
    trace = dict_value(report, "trace")
    langsmith = dict_value(report, "langsmith")
    return {
        "path": str(path),
        "present": bool(report),
        "status": report.get("status", "missing"),
        "failed": report.get("failed", 0),
        "trace_status": trace.get("status", "missing"),
        "trace_total_runs": trace.get("total_runs", 0),
        "langsmith_enabled": langsmith.get("enabled", False),
    }


def summarize_real_replay_coverage(
    report: dict[str, object], path: Path
) -> dict[str, object]:
    fixture = str(report.get("fixture", ""))
    normalized_fixture = fixture.replace("\\", "/").lower()
    is_real_fixture = bool(fixture) and "tests/fixtures/" not in normalized_fixture
    return {
        "path": str(path),
        "present": bool(report),
        "status": report.get("status", "missing"),
        "failed": report.get("failed", 0),
        "fixture": fixture,
        "real_fixture_coverage_verified": report.get("status") == "passed"
        and report.get("failed") == 0
        and is_real_fixture,
    }


def summarize_release_packet(
    report: dict[str, object], release_report_path: Path
) -> dict[str, object]:
    real_replay = dict_value(report, "real_replay")
    return {
        "release_report_path": str(release_report_path),
        "status": report.get("status", "missing"),
        "app_version": report.get("app_version", ""),
        "packet_ready": report.get("packet_ready", False),
        "candidate_audit": dict_value(real_replay, "candidate_audit"),
        "intake_readiness": dict_value(real_replay, "intake_readiness"),
        "langsmith": dict_value(report, "langsmith"),
        "rag": dict_value(report, "rag"),
    }


def build_stage_readiness(
    evidence: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    release = evidence["release"]
    candidate_audit = dict_value(release, "candidate_audit")
    intake_readiness = dict_value(release, "intake_readiness")
    langsmith = dict_value(release, "langsmith")
    real_sample_ready = intake_readiness.get("real_sample_ready") is True
    return {
        "E1_real_replay": {
            "ready": candidate_audit.get("candidate_ready") is True
            and real_sample_ready,
            "action": "provide_and_approve_redacted_real_replay_samples",
        },
        "E2_real_rag_shadow_log": {
            "ready": evidence["rag_shadow_log"].get("shadow_log_ready") is True,
            "action": "provide_redacted_rag_shadow_log_input",
        },
        "E3_planned_hybrid_gray_release": {
            "ready": evidence["rag_gray_release"].get("gray_release_verified") is True,
            "action": "complete_controlled_planned_hybrid_gray_release",
        },
        "E4_langsmith_production_export": {
            "ready": langsmith.get("enabled") is True
            and evidence["langsmith_production_export"].get("external_export_verified")
            is True,
            "action": "obtain_export_approval_and_enable_langsmith_sampling",
        },
        "E5_real_fact_sensitive_coverage": {
            "ready": real_sample_ready
            and evidence["real_replay_coverage"].get("real_fixture_coverage_verified")
            is True,
            "action": "cover_each_fact_sensitive_scenario_with_real_replays",
        },
    }


def build_assertions(
    architecture: dict[str, object],
    evidence: dict[str, dict[str, object]],
) -> dict[str, bool]:
    agent_eval = evidence["agent_eval"]
    rag_shadow = evidence["rag_shadow"]
    observability = evidence["observability"]
    release = evidence["release"]
    return {
        "architecture.code_paths_present": not architecture["missing_paths"],
        "agent_eval.current_version_passed": agent_eval.get("status") == "passed"
        and agent_eval.get("failed") == 0
        and agent_eval.get("app_version") == APP_VERSION,
        "rag_shadow.report_passed": rag_shadow.get("status") == "passed"
        and rag_shadow.get("failed") == 0,
        "observability.report_passed": observability.get("status") == "passed"
        and observability.get("failed") == 0
        and observability.get("trace_status") == "ok",
        "release.packet_ready": release.get("status") == "passed"
        and release.get("packet_ready") is True
        and release.get("app_version") == APP_VERSION,
    }


def count_failed_assertions(
    *,
    verified_evidence_ready: bool,
    portfolio_complete: bool,
    require_verified_evidence: bool,
    require_complete: bool,
) -> int:
    failed = 0
    if require_verified_evidence and not verified_evidence_ready:
        failed += 1
    if require_complete and not portfolio_complete:
        failed += 1
    return failed


def build_missing_actions(
    assertions: dict[str, bool],
    stage_readiness: dict[str, dict[str, object]],
) -> list[str]:
    assertion_actions = {
        "architecture.code_paths_present": "restore_portfolio_code_path_references",
        "agent_eval.current_version_passed": "refresh_current_version_agent_eval",
        "rag_shadow.report_passed": "refresh_rag_shadow_observability_report",
        "observability.report_passed": "refresh_langchain_observability_evidence",
        "release.packet_ready": "refresh_strict_production_release_evidence",
    }
    actions = [
        action
        for assertion, action in assertion_actions.items()
        if assertions.get(assertion) is False
    ]
    actions.extend(
        str(stage["action"])
        for stage in stage_readiness.values()
        if stage.get("ready") is False
    )
    return actions


def build_boundaries() -> dict[str, bool]:
    return {
        "business_database_read": False,
        "external_llm_called": False,
        "production_service_changed": False,
        "raw_customer_conversation_read": False,
        "real_customer_data_committed": False,
        "missing_external_evidence_treated_as_complete": False,
    }


def read_json_report(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def dict_value(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成 LangChain AI 应用层作品集证据清单"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument(
        "--json-out", type=Path, default=DEFAULT_OUTPUT_PATH, help="证据清单输出路径"
    )
    parser.add_argument(
        "--require-verified-evidence",
        action="store_true",
        help="要求当前版本的本地与生产证据齐全",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="要求 E1-E5 外部证据与当前工程证据全部完成",
    )
    add_evidence_path_arguments(parser)
    return parser.parse_args(argv)


def add_evidence_path_arguments(parser: argparse.ArgumentParser) -> None:
    defaults = PortfolioEvidencePaths()
    parser.add_argument("--agent-eval", type=Path, default=defaults.agent_eval)
    parser.add_argument("--rag-shadow", type=Path, default=defaults.rag_shadow)
    parser.add_argument("--rag-shadow-log", type=Path, default=defaults.rag_shadow_log)
    parser.add_argument(
        "--rag-gray-release", type=Path, default=defaults.rag_gray_release
    )
    parser.add_argument(
        "--langsmith-production-export",
        type=Path,
        default=defaults.langsmith_production_export,
    )
    parser.add_argument("--observability", type=Path, default=defaults.observability)
    parser.add_argument(
        "--real-replay-coverage", type=Path, default=defaults.real_replay_coverage
    )
    parser.add_argument("--release-report", type=Path, default=defaults.release_report)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    paths = PortfolioEvidencePaths(
        agent_eval=args.agent_eval,
        rag_shadow=args.rag_shadow,
        rag_shadow_log=args.rag_shadow_log,
        rag_gray_release=args.rag_gray_release,
        langsmith_production_export=args.langsmith_production_export,
        observability=args.observability,
        real_replay_coverage=args.real_replay_coverage,
        release_report=args.release_report,
    )
    report = build_portfolio_evidence_packet(
        paths=paths,
        require_verified_evidence=args.require_verified_evidence,
        require_complete=args.require_complete,
    )
    write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print_summary(report)
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def write_json_report(report: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def print_summary(report: dict[str, object]) -> None:
    print(
        "langchain_portfolio_evidence_packet "
        f"status={report['status']} "
        f"verified_evidence_ready={str(report['verified_evidence_ready']).lower()} "
        f"external_evidence_complete={str(report['external_evidence_complete']).lower()} "
        f"portfolio_complete={str(report['portfolio_complete']).lower()} "
        f"failed={report['failed']}"
    )


def print_text_report(report: dict[str, object]) -> None:
    print_summary(report)
    for action in report["missing_actions"]:
        print(f"NEXT {action}")


if __name__ == "__main__":
    raise SystemExit(main())
