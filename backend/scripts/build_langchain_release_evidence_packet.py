"""生成 LangChain AI 应用层发布证据包。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from scripts import check_langchain_production_observability_release as release_check  # noqa: E402
from scripts.audit_real_conversation_replay_candidate import (  # noqa: E402
    build_real_replay_candidate_audit_report,
)
from scripts.check_real_conversation_replay_intake_readiness import (  # noqa: E402
    build_real_replay_intake_readiness_report,
)

DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "harness" / "langchain-release-evidence-packet.json"
)
DEFAULT_RELEASE_REPORT_PATH = release_check.DEFAULT_RELEASE_REPORT_PATH
UNKNOWN_VALUE = "unknown"
NOT_CHECKED = "not_checked"


def build_release_evidence_packet(
    *,
    release_report_path: Path = DEFAULT_RELEASE_REPORT_PATH,
    require_production_evidence: bool = False,
    production_commit: str = NOT_CHECKED,
    production_version: str = NOT_CHECKED,
    production_service_status: str = NOT_CHECKED,
) -> dict[str, object]:
    release_report = read_json_report(release_report_path)
    production_release = build_production_release_summary(release_report_path)
    git_refs = build_git_refs(
        production_commit=production_commit,
        production_version=production_version,
        production_service_status=production_service_status,
    )
    candidate_audit = build_real_replay_candidate_audit_report()
    intake_readiness = build_real_replay_intake_readiness_report()
    assertions = build_assertions(
        release_report=release_report,
        production_release=production_release,
        require_production_evidence=require_production_evidence,
    )
    failed = count_failed_assertions(
        assertions,
        require_production_evidence=require_production_evidence,
    )
    packet_ready = (
        bool(release_report)
        and assertions["release_gate.passed"]
        and assertions["production_observability_release.passed"]
    )
    return {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": utc_now(),
        "trace_id": "20260709-langchain-ai-layer-production-enhancement",
        "app_version": APP_VERSION,
        "release_report": str(release_report_path),
        "require_production_evidence": require_production_evidence,
        "packet_ready": packet_ready,
        "failed": failed,
        "assertions": assertions,
        "missing_actions": build_missing_actions(assertions),
        "git": git_refs,
        "release_gate": summarize_release_gate(release_report),
        "production_observability_release": summarize_production_release(
            production_release
        ),
        "langsmith": summarize_langsmith(release_report),
        "rag": summarize_rag(release_report),
        "real_replay": {
            "candidate_audit": summarize_candidate_audit(candidate_audit),
            "intake_readiness": summarize_intake_readiness(intake_readiness),
        },
        "rollback_commands": build_rollback_commands(),
        "boundaries": {
            "business_database_read": False,
            "external_llm_called": False,
            "production_service_changed": False,
            "real_customer_data_committed": False,
            "raw_customer_conversation_read": False,
        },
    }


def build_assertions(
    *,
    release_report: dict[str, object],
    production_release: dict[str, object],
    require_production_evidence: bool,
) -> dict[str, bool]:
    release_present = bool(release_report)
    production_release_passed = production_release.get("status") == "passed"
    assertions = {
        "release_report.present": release_present,
        "release_gate.passed": not release_present
        or release_report.get("status") == "passed",
        "production_observability_release.passed": not release_present
        or production_release_passed,
    }
    if require_production_evidence:
        assertions["require_production_evidence.release_report_present"] = (
            release_present
        )
        assertions["require_production_evidence.production_release_passed"] = (
            production_release_passed
        )
    return assertions


def count_failed_assertions(
    assertions: dict[str, bool],
    *,
    require_production_evidence: bool,
) -> int:
    blocking_names: list[str] = []
    if require_production_evidence:
        blocking_names.extend(
            [
                "require_production_evidence.release_report_present",
                "require_production_evidence.production_release_passed",
            ]
        )
    return sum(1 for name in blocking_names if assertions.get(name) is False)


def build_missing_actions(assertions: dict[str, bool]) -> list[str]:
    action_by_assertion = {
        "release_report.present": "run_langchain_release_gate_with_production_evidence",
        "release_gate.passed": "fix_failed_release_gate_steps",
        "production_observability_release.passed": "fix_production_observability_release_findings",
        "require_production_evidence.release_report_present": "provide_release_gate_json_report",
        "require_production_evidence.production_release_passed": "rerun_p13b_production_observability_release_gate",
    }
    return [
        action
        for assertion, action in action_by_assertion.items()
        if assertions.get(assertion) is False
    ]


def build_git_refs(
    *,
    production_commit: str,
    production_version: str,
    production_service_status: str,
) -> dict[str, object]:
    local_commit = run_git_command(("git", "rev-parse", "HEAD"))
    origin_commit = run_git_command(("git", "rev-parse", "origin/master"))
    server_commit = run_git_command(("git", "rev-parse", "server/master"))
    return {
        "local_commit": local_commit,
        "origin_master": origin_commit,
        "server_master": server_commit,
        "production_commit": production_commit,
        "production_version": production_version,
        "production_service_status": production_service_status,
        "local_matches_origin": local_commit == origin_commit,
        "local_matches_server": local_commit == server_commit,
    }


def build_production_release_summary(release_report_path: Path) -> dict[str, object]:
    if not release_report_path.exists():
        return {"status": "missing", "failed": 1, "findings": []}
    return release_check.build_production_observability_release_report(
        release_report_path
    )


def summarize_release_gate(release_report: dict[str, object]) -> dict[str, object]:
    release_summary = dict_value(release_report, "release_summary")
    return {
        "status": release_report.get("status", "missing"),
        "total": release_report.get("total", 0),
        "failed": release_report.get("failed", 0),
        "agent_eval_default": release_summary.get("agent_eval_default"),
        "agent_eval_with_reply_replay": release_summary.get(
            "agent_eval_with_reply_replay"
        ),
        "production_smoke": release_summary.get("production_smoke"),
        "production_employee_callback_probe": release_summary.get(
            "production_employee_callback_probe"
        ),
        "langchain_ai_layer_capacity": release_summary.get(
            "langchain_ai_layer_capacity"
        ),
    }


def summarize_production_release(report: dict[str, object]) -> dict[str, object]:
    production = dict_value(report, "production")
    observability = dict_value(report, "observability")
    capacity = dict_value(report, "capacity")
    return {
        "status": report.get("status", "missing"),
        "failed": report.get("failed", 0),
        "expected_app_version": report.get("expected_app_version", APP_VERSION),
        "endpoint_versions": production.get("endpoint_versions", {}),
        "callback_failed": production.get("callback_failed", 0),
        "langsmith_enabled": observability.get("langsmith_enabled"),
        "capacity_runtime": capacity.get("production_runtime_status", "missing"),
        "findings": report.get("findings", []),
    }


def summarize_langsmith(release_report: dict[str, object]) -> dict[str, object]:
    runtime_config = dict_value(
        dict_value(release_report, "release_summary"),
        "langsmith_runtime_config",
    )
    return {
        "enabled": runtime_config.get("enabled", False),
        "safe_to_enable": runtime_config.get("safe_to_enable", False),
        "project": runtime_config.get("project", ""),
        "api_key_configured": runtime_config.get("api_key_configured", False),
    }


def summarize_rag(release_report: dict[str, object]) -> dict[str, object]:
    rag_matrix = dict_value(
        dict_value(release_report, "release_summary"), "rag_eval_matrix"
    )
    return {
        "configured_mode": os.getenv("RAG_RETRIEVAL_MODE", "hybrid"),
        "matrix_status": rag_matrix.get("status", "not_included"),
        "best": rag_matrix.get("best", {}),
    }


def summarize_candidate_audit(report: dict[str, object]) -> dict[str, object]:
    return {
        "status": report.get("status", "missing"),
        "candidate_ready": report.get("candidate_ready", False),
        "missing_actions": report.get("missing_actions", []),
    }


def summarize_intake_readiness(report: dict[str, object]) -> dict[str, object]:
    return {
        "status": report.get("status", "missing"),
        "real_sample_ready": report.get("real_sample_ready", False),
        "missing_actions": report.get("missing_actions", []),
    }


def build_rollback_commands() -> list[str]:
    return [
        "恢复 RAG_RETRIEVAL_MODE=hybrid 并重启服务",
        "关闭 LangSmith tracing 环境变量并重启服务",
        "git revert <bad_commit> 后推送 origin/server，再在生产 fast-forward",
        "systemctl restart yunxibakebot",
        "python scripts\\check_langchain_production_runtime_version.py --summary",
        "python scripts\\check_langchain_ai_layer_release_gate.py --include-production-smoke --include-observability-evidence --include-production-runtime-capacity --json-out reports\\agent-eval\\langchain-ai-layer-release-gate-with-production-observability-latest.json --summary",
    ]


def run_git_command(command: tuple[str, ...]) -> str:
    completed = subprocess.run(
        command,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return UNKNOWN_VALUE
    return completed.stdout.strip()


def read_json_report(path: Path) -> dict[str, object]:
    if not path.exists():
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
        description="Build LangChain release evidence packet"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="写入发布证据包 JSON 路径",
    )
    parser.add_argument(
        "--release-report",
        type=Path,
        default=DEFAULT_RELEASE_REPORT_PATH,
        help="LangChain release gate JSON 报告路径",
    )
    parser.add_argument(
        "--require-production-evidence",
        action="store_true",
        help="要求已有生产 release gate 和 P13b 复核证据通过",
    )
    parser.add_argument("--production-commit", default=NOT_CHECKED)
    parser.add_argument("--production-version", default=NOT_CHECKED)
    parser.add_argument("--production-service-status", default=NOT_CHECKED)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_release_evidence_packet(
        release_report_path=args.release_report,
        require_production_evidence=args.require_production_evidence,
        production_commit=args.production_commit,
        production_version=args.production_version,
        production_service_status=args.production_service_status,
    )
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "langchain_release_evidence_packet "
            f"status={report['status']} "
            f"packet_ready={str(report['packet_ready']).lower()} "
            f"failed={report['failed']}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_text_report(report: dict[str, object]) -> None:
    print("langchain_release_evidence_packet")
    print(
        f"status={report['status']} "
        f"packet_ready={report['packet_ready']} failed={report['failed']}"
    )
    for action in report["missing_actions"]:
        print(f"NEXT {action}")


if __name__ == "__main__":
    raise SystemExit(main())
