"""LangSmith 运行时配置预检。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from app.service.agents.evaluation import write_json_report  # noqa: E402
from app.service.agents.observability import (  # noqa: E402
    AgentTracingConfig,
    get_agent_tracing_config,
)

DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "agent-traces" / "langsmith-runtime-config.json"
)
TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})
SENSITIVE_SAMPLE_METADATA = {
    "case_id": "langsmith-preflight",
    "agent": "customer",
    "tool_count": 2,
    "api_key": "sample-secret-api-key",
    "access_token": "sample-secret-token",
    "open_id": "sample-open-id",
    "phone": "13800000000",
    "mobile": "13900000000",
    "address": "样例地址不应外发",
    "messages": ["用户原文不应外发"],
    "history_text": "历史消息不应外发",
    "customer_profile": {"nickname": "样例客户"},
    "tool_result": {"order_id": "sample-order"},
}
SENSITIVE_MARKERS = (
    "sample-secret-api-key",
    "sample-secret-token",
    "sample-open-id",
    "13800000000",
    "13900000000",
    "样例地址不应外发",
    "用户原文不应外发",
    "历史消息不应外发",
    "样例客户",
    "sample-order",
)


def build_langsmith_runtime_config_report(
    *,
    require_enabled: bool = False,
    config: AgentTracingConfig | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, object]:
    tracing_config = config or get_agent_tracing_config()
    env = dict(os.environ if environ is None else environ)
    project = resolve_project(tracing_config, env)
    tracing_requested = is_tracing_requested(tracing_config, env)
    api_key_configured = is_api_key_configured(tracing_config, env)
    sanitized_runnable_config = build_sanitized_runnable_config(tracing_config)
    sensitive_markers_found = find_sensitive_markers(
        sanitized_runnable_config,
        SENSITIVE_MARKERS,
    )
    missing = build_missing_requirements(
        tracing_requested=tracing_requested,
        require_enabled=require_enabled,
        project=project,
        api_key_configured=api_key_configured,
    )
    safe_to_enable = (
        api_key_configured
        and bool(project)
        and not sensitive_markers_found
        and not missing
    )
    status = "passed"
    if missing or sensitive_markers_found:
        status = "failed"
    return {
        "status": status,
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "require_enabled": require_enabled,
        "runtime": {
            "tracing_requested": tracing_requested,
            "enabled": tracing_requested and api_key_configured,
            "runtime_config_enabled": tracing_config.is_langsmith_enabled,
            "safe_to_enable": safe_to_enable,
            "project": project,
            "api_key_configured": api_key_configured,
            "api_key_redacted": api_key_configured,
            "missing": missing,
        },
        "env": {
            "LANGCHAIN_TRACING_ENABLED": tracing_config.langchain_tracing_enabled,
            "LANGCHAIN_TRACING_V2": redact_env_flag(env, "LANGCHAIN_TRACING_V2"),
            "LANGSMITH_TRACING": redact_env_flag(env, "LANGSMITH_TRACING"),
            "LANGCHAIN_PROJECT": project,
            "LANGSMITH_API_KEY": "configured"
            if has_env_value(env, "LANGSMITH_API_KEY")
            else "",
            "LANGCHAIN_API_KEY": "configured"
            if has_env_value(env, "LANGCHAIN_API_KEY")
            else "",
        },
        "metadata_redaction": {
            "status": "passed" if not sensitive_markers_found else "failed",
            "sample": sanitized_runnable_config,
            "sensitive_markers_found": sensitive_markers_found,
        },
        "boundaries": {
            "external_llm_called": False,
            "langsmith_external_export": False,
            "business_database_read": False,
            "production_hot_path_changed": False,
            "contains_sensitive_data": bool(sensitive_markers_found),
        },
    }


def resolve_project(config: AgentTracingConfig, env: dict[str, str]) -> str:
    env_project = env.get("LANGCHAIN_PROJECT", "").strip()
    return env_project or config.langchain_project


def is_tracing_requested(config: AgentTracingConfig, env: dict[str, str]) -> bool:
    return (
        config.langchain_tracing_enabled
        or is_truthy(env.get("LANGCHAIN_TRACING_V2", ""))
        or is_truthy(env.get("LANGSMITH_TRACING", ""))
    )


def is_api_key_configured(config: AgentTracingConfig, env: dict[str, str]) -> bool:
    return bool(
        config.langsmith_api_key
        or env.get("LANGSMITH_API_KEY", "").strip()
        or env.get("LANGCHAIN_API_KEY", "").strip()
    )


def build_sanitized_runnable_config(config: AgentTracingConfig) -> dict[str, Any]:
    return config.to_runnable_config(
        run_name="langsmith_runtime_config_preflight",
        tags=("preflight", "langsmith"),
        metadata=SENSITIVE_SAMPLE_METADATA,
    )


def find_sensitive_markers(
    payload: dict[str, Any],
    markers: tuple[str, ...],
) -> list[str]:
    serialized_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return [marker for marker in markers if marker in serialized_payload]


def build_missing_requirements(
    *,
    tracing_requested: bool,
    require_enabled: bool,
    project: str,
    api_key_configured: bool,
) -> list[str]:
    should_validate_enabled = tracing_requested or require_enabled
    missing = []
    if should_validate_enabled and not project:
        missing.append("LANGCHAIN_PROJECT")
    if should_validate_enabled and not api_key_configured:
        missing.append("LANGSMITH_API_KEY")
    if require_enabled and not tracing_requested:
        missing.append("LANGCHAIN_TRACING_ENABLED")
    return missing


def redact_env_flag(env: dict[str, str], key: str) -> str:
    value = env.get(key)
    if value is None:
        return ""
    return "true" if is_truthy(value) else "false"


def has_env_value(env: dict[str, str], key: str) -> bool:
    return bool(env.get(key, "").strip())


def is_truthy(value: str) -> bool:
    return value.strip().lower() in TRUTHY_VALUES


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check LangSmith runtime config")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="写入 LangSmith 预检 JSON 路径",
    )
    parser.add_argument(
        "--require-enabled",
        action="store_true",
        help="要求 LangSmith tracing 已完整启用",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_langsmith_runtime_config_report(
        require_enabled=args.require_enabled,
    )
    if args.json_out is not None:
        write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        runtime = report["runtime"]
        print(
            "langsmith_runtime_config "
            f"status={report['status']} "
            f"enabled={str(runtime['enabled']).lower()} "
            f"safe_to_enable={str(runtime['safe_to_enable']).lower()} "
            f"missing={len(runtime['missing'])}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_text_report(report: dict[str, object]) -> None:
    runtime = report["runtime"]
    metadata_redaction = report["metadata_redaction"]
    print("langsmith_runtime_config")
    print(
        f"status={report['status']} "
        f"enabled={str(runtime['enabled']).lower()} "
        f"safe_to_enable={str(runtime['safe_to_enable']).lower()}"
    )
    print(f"project={runtime['project']}")
    print(f"api_key_configured={str(runtime['api_key_configured']).lower()}")
    print(f"metadata_redaction={metadata_redaction['status']}")
    for item in runtime["missing"]:
        print(f"FAIL missing {item}")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
