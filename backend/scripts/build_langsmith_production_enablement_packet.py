"""生成 LangSmith 生产启用操作包。"""

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
from scripts.check_langsmith_production_rollout import (  # noqa: E402
    DEFAULT_PROJECT,
    MAX_DEFAULT_SAMPLE_RATE,
    ROLLBACK_COMMANDS,
)

DEFAULT_OUTPUT_PATH = (
    ROOT_DIR
    / "reports"
    / "agent-traces"
    / "langsmith-production-enablement-packet.json"
)
DEFAULT_SAMPLE_RATE = 0.05
REQUIRED_ENV_VARS = (
    {
        "name": "LANGCHAIN_TRACING_ENABLED",
        "expected": "true",
        "contains_secret": False,
        "description": "打开项目内部 LangChain tracing 开关",
    },
    {
        "name": "LANGCHAIN_TRACING_V2",
        "expected": "true",
        "contains_secret": False,
        "description": "打开 LangChain v2 tracing 协议",
    },
    {
        "name": "LANGSMITH_TRACING",
        "expected": "true",
        "contains_secret": False,
        "description": "打开 LangSmith tracing 开关",
    },
    {
        "name": "LANGCHAIN_PROJECT",
        "expected": "<project>",
        "contains_secret": False,
        "description": "生产 LangSmith project 名称",
    },
    {
        "name": "LANGSMITH_API_KEY",
        "expected": "<configured outside repo>",
        "contains_secret": True,
        "description": "只在生产环境配置，不写入仓库或报告",
    },
)
PRE_ENABLE_COMMANDS = (
    "python scripts\\check_langsmith_runtime_config.py --require-enabled --summary",
    (
        "python scripts\\check_langsmith_production_rollout.py "
        "--require-enabled --external-export-approved "
        f"--sample-rate {DEFAULT_SAMPLE_RATE} --summary"
    ),
)
POST_ENABLE_COMMANDS = (
    "python scripts\\report_langchain_observability_evidence.py --summary",
    (
        "python scripts\\check_langchain_ai_layer_release_gate.py "
        "--include-production-smoke --include-observability-evidence --summary"
    ),
)
MANUAL_APPROVALS = (
    "已确认生产 trace 外发合规边界",
    "已确认 metadata 脱敏报告通过且不包含客户原文",
    "已确认采样率不超过安全上限",
    "已确认回滚命令和服务重启权限",
)


def build_langsmith_enablement_packet(
    *,
    project: str = DEFAULT_PROJECT,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
    operator: str = "manual_operator",
    evidence_id: str = "E-P18B-LANGSMITH-ENABLEMENT",
) -> dict[str, object]:
    assertions = build_packet_assertions(
        project=project,
        sample_rate=sample_rate,
        operator=operator,
        evidence_id=evidence_id,
    )
    failed = sum(1 for passed in assertions.values() if not passed)
    return {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "failed": failed,
        "operator": operator,
        "evidence_id": evidence_id,
        "project": project,
        "sample_rate": sample_rate,
        "max_default_sample_rate": MAX_DEFAULT_SAMPLE_RATE,
        "required_env_vars": build_required_env_vars(project),
        "manual_approvals": list(MANUAL_APPROVALS),
        "commands": build_command_plan(sample_rate=sample_rate),
        "assertions": assertions,
        "boundaries": {
            "production_env_changed": False,
            "langsmith_external_export": False,
            "api_key_printed": False,
            "api_key_committed": False,
            "business_database_read": False,
            "external_llm_called": False,
            "contains_sensitive_data": False,
        },
        "next_gate": (
            "python scripts\\check_langsmith_production_rollout.py "
            "--require-enabled --external-export-approved "
            f"--sample-rate {sample_rate} --summary"
        ),
    }


def build_required_env_vars(project: str) -> list[dict[str, object]]:
    env_vars: list[dict[str, object]] = []
    for item in REQUIRED_ENV_VARS:
        value = project if item["name"] == "LANGCHAIN_PROJECT" else item["expected"]
        env_vars.append({**item, "expected": value})
    return env_vars


def build_packet_assertions(
    *,
    project: str,
    sample_rate: float,
    operator: str,
    evidence_id: str,
) -> dict[str, bool]:
    env_vars = build_required_env_vars(project)
    return {
        "project.present": bool(project.strip()),
        "sample_rate.within_safe_default": 0.0 < sample_rate <= MAX_DEFAULT_SAMPLE_RATE,
        "operator.present": bool(operator.strip()),
        "evidence_id.present": bool(evidence_id.strip()),
        "required_env_vars.complete": len(env_vars) == len(REQUIRED_ENV_VARS),
        "api_key.not_materialized": all(
            item["expected"] != "sk-" and not str(item["expected"]).startswith("lsv2_")
            for item in env_vars
        ),
        "pre_enable_commands.present": bool(PRE_ENABLE_COMMANDS),
        "rollback_commands.present": set(ROLLBACK_COMMANDS)
        == {
            "LANGCHAIN_TRACING_ENABLED=false",
            "LANGCHAIN_TRACING_V2=false",
            "LANGSMITH_TRACING=false",
            "systemctl restart yunxibakebot",
        },
    }


def build_command_plan(*, sample_rate: float) -> dict[str, list[str]]:
    return {
        "pre_enable": [
            command.replace(str(DEFAULT_SAMPLE_RATE), str(sample_rate))
            for command in PRE_ENABLE_COMMANDS
        ],
        "enable_env": [
            "LANGCHAIN_TRACING_ENABLED=true",
            "LANGCHAIN_TRACING_V2=true",
            "LANGSMITH_TRACING=true",
            "LANGCHAIN_PROJECT=<project>",
            "LANGSMITH_API_KEY=<configured outside repo>",
        ],
        "post_enable": [
            command.replace(str(DEFAULT_SAMPLE_RATE), str(sample_rate))
            for command in POST_ENABLE_COMMANDS
        ],
        "rollback": list(ROLLBACK_COMMANDS),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build LangSmith production enablement packet"
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="LangSmith project")
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=DEFAULT_SAMPLE_RATE,
        help="计划生产外发采样率",
    )
    parser.add_argument("--operator", default="manual_operator", help="执行或审核人")
    parser.add_argument(
        "--evidence-id",
        default="E-P18B-LANGSMITH-ENABLEMENT",
        help="证据索引 ID",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="写入 LangSmith 生产启用操作包 JSON 路径",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_langsmith_enablement_packet(
        project=args.project,
        sample_rate=args.sample_rate,
        operator=args.operator,
        evidence_id=args.evidence_id,
    )
    if args.json_out is not None:
        write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "langsmith_production_enablement_packet "
            f"status={report['status']} failed={report['failed']} "
            f"sample_rate={report['sample_rate']}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_text_report(report: dict[str, object]) -> None:
    print("langsmith_production_enablement_packet")
    print(
        f"status={report['status']} failed={report['failed']} "
        f"sample_rate={report['sample_rate']}"
    )
    commands = report["commands"]
    for command in commands["pre_enable"]:
        print(f"PRE {command}")
    for command in commands["rollback"]:
        print(f"ROLLBACK {command}")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
