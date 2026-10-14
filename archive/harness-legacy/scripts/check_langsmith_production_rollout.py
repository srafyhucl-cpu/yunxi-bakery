"""LangSmith 生产灰度发布预检。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from app.service.agents.evaluation import write_json_report  # noqa: E402
from scripts.check_langsmith_runtime_config import (  # noqa: E402
    build_langsmith_runtime_config_report,
)
from scripts.report_langchain_observability_evidence import (  # noqa: E402
    COLD_IMPORT_TARGETS,
    build_cold_import_summary,
)

DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "agent-traces" / "langsmith-production-rollout.json"
)
DEFAULT_PROJECT = "yunxi-bakebot"
MAX_DEFAULT_SAMPLE_RATE = 0.1
ROLLBACK_COMMANDS = (
    "LANGCHAIN_TRACING_ENABLED=false",
    "LANGCHAIN_TRACING_V2=false",
    "LANGSMITH_TRACING=false",
    "systemctl restart yunxibakebot",
)


def build_langsmith_production_rollout_report(
    *,
    sample_rate: float = 0.0,
    require_enabled: bool = False,
    external_export_approved: bool = False,
    project: str = DEFAULT_PROJECT,
) -> dict[str, object]:
    runtime_config = build_langsmith_runtime_config_report(
        require_enabled=require_enabled,
    )
    cold_imports = [build_cold_import_summary(target) for target in COLD_IMPORT_TARGETS]
    assertions = build_assertions(
        runtime_config=runtime_config,
        cold_imports=cold_imports,
        sample_rate=sample_rate,
        require_enabled=require_enabled,
        external_export_approved=external_export_approved,
        project=project,
    )
    failed = sum(1 for passed in assertions.values() if not passed)
    enabled = bool(runtime_config["runtime"]["enabled"])
    return {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "failed": failed,
        "require_enabled": require_enabled,
        "rollout": {
            "enabled": enabled,
            "project": project,
            "sample_rate": sample_rate,
            "external_export_approved": external_export_approved,
            "max_default_sample_rate": MAX_DEFAULT_SAMPLE_RATE,
            "rollback_commands": list(ROLLBACK_COMMANDS),
        },
        "runtime_config": summarize_runtime_config(runtime_config),
        "cold_imports": cold_imports,
        "assertions": assertions,
        "missing_actions": build_missing_actions(assertions),
        "boundaries": {
            "production_env_changed": False,
            "langsmith_external_export": False,
            "external_llm_called": False,
            "business_database_read": False,
            "contains_sensitive_data": False,
        },
    }


def build_assertions(
    *,
    runtime_config: dict[str, object],
    cold_imports: list[dict[str, object]],
    sample_rate: float,
    require_enabled: bool,
    external_export_approved: bool,
    project: str,
) -> dict[str, bool]:
    runtime = runtime_config["runtime"]
    metadata_redaction = runtime_config["metadata_redaction"]
    sample_rate_valid = 0.0 <= sample_rate <= MAX_DEFAULT_SAMPLE_RATE
    return {
        "project.present": bool(project.strip()),
        "sample_rate.within_safe_default": sample_rate_valid,
        "metadata_redaction.passed": metadata_redaction.get("status") == "passed",
        "cold_imports.passed": all(
            item.get("status") == "passed" for item in cold_imports
        ),
        "runtime_config.passed": runtime_config.get("status") == "passed",
        "runtime_config.safe_to_enable": (not require_enabled)
        or bool(runtime.get("safe_to_enable")),
        "external_export.approved": (not require_enabled) or external_export_approved,
        "rollback_commands.present": all(ROLLBACK_COMMANDS),
    }


def summarize_runtime_config(report: dict[str, object]) -> dict[str, object]:
    runtime = report["runtime"]
    metadata_redaction = report["metadata_redaction"]
    return {
        "status": report.get("status"),
        "enabled": runtime.get("enabled", False),
        "safe_to_enable": runtime.get("safe_to_enable", False),
        "project": runtime.get("project", ""),
        "api_key_configured": runtime.get("api_key_configured", False),
        "missing": runtime.get("missing", []),
        "metadata_redaction_status": metadata_redaction.get("status", "missing"),
    }


def build_missing_actions(assertions: dict[str, bool]) -> list[str]:
    actions = []
    if not assertions["sample_rate.within_safe_default"]:
        actions.append("lower_langsmith_sample_rate_to_safe_default")
    if not assertions["runtime_config.safe_to_enable"]:
        actions.append("configure_langsmith_project_api_key_and_tracing_flag")
    if not assertions["external_export.approved"]:
        actions.append("approve_langsmith_external_export_compliance")
    if not assertions["cold_imports.passed"]:
        actions.append("fix_heavy_import_before_production_rollout")
    if not assertions["metadata_redaction.passed"]:
        actions.append("fix_trace_metadata_redaction_before_external_export")
    return actions


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check LangSmith production rollout readiness"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="写入 LangSmith 生产灰度预检 JSON 路径",
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=0.0,
        help="计划灰度采样率，默认 0 表示不外发",
    )
    parser.add_argument(
        "--require-enabled",
        action="store_true",
        help="要求 LangSmith 外发已满足启用条件",
    )
    parser.add_argument(
        "--external-export-approved",
        action="store_true",
        help="声明已完成人工外发合规确认",
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="LangSmith project")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_langsmith_production_rollout_report(
        sample_rate=args.sample_rate,
        require_enabled=args.require_enabled,
        external_export_approved=args.external_export_approved,
        project=args.project,
    )
    if args.json_out is not None:
        write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        rollout = report["rollout"]
        print(
            "langsmith_production_rollout "
            f"status={report['status']} failed={report['failed']} "
            f"enabled={str(rollout['enabled']).lower()} "
            f"sample_rate={rollout['sample_rate']}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_text_report(report: dict[str, object]) -> None:
    rollout = report["rollout"]
    print("langsmith_production_rollout")
    print(
        f"status={report['status']} failed={report['failed']} "
        f"enabled={str(rollout['enabled']).lower()} "
        f"sample_rate={rollout['sample_rate']}"
    )
    for action in report["missing_actions"]:
        print(f"NEXT {action}")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
