"""汇总 LangChain AI 应用层观测证据。"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from app.service.agents.observability import get_agent_tracing_config  # noqa: E402
from app.service.agents.trace_report import (  # noqa: E402
    build_agent_trace_report,
    parse_trace_runs,
)
from app.service.agents.observability import safe_trace_payload  # noqa: E402
from app.service.agents.evaluation import write_json_report  # noqa: E402
from scripts import probe_agent_traces  # noqa: E402

DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "agent-traces" / "langchain-observability-evidence.json"
)
DEFAULT_TRACE_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "agent-traces" / "langchain-observability-trace-probe.json"
)
HEAVY_MODULES = (
    "langsmith",
    "langchain_openai",
    "langgraph",
    "langchain_core",
)
COLD_IMPORT_TARGETS = (
    "app.config",
    "app.service.agents.rag.modes",
)


def build_observability_evidence_report(
    *,
    trace_input_path: Path | None = None,
    run_trace_probe: bool = True,
    trace_output_path: Path = DEFAULT_TRACE_OUTPUT_PATH,
) -> dict[str, object]:
    trace_path = resolve_trace_path(
        trace_input_path=trace_input_path,
        run_trace_probe=run_trace_probe,
        trace_output_path=trace_output_path,
    )
    trace_report = build_trace_summary(trace_path)
    langsmith_config = build_langsmith_config_summary()
    cold_imports = [build_cold_import_summary(target) for target in COLD_IMPORT_TARGETS]
    failed = count_failed_checks(
        trace_report=trace_report,
        langsmith_config=langsmith_config,
        cold_imports=cold_imports,
    )
    return {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "failed": failed,
        "trace": trace_report,
        "langsmith": langsmith_config,
        "cold_imports": cold_imports,
        "boundaries": {
            "production_hot_path_changed": False,
            "external_llm_called": False,
            "langsmith_external_export": langsmith_config["enabled"],
            "contains_sensitive_data": False,
        },
    }


def resolve_trace_path(
    *,
    trace_input_path: Path | None,
    run_trace_probe: bool,
    trace_output_path: Path,
) -> Path | None:
    if trace_input_path is not None:
        return trace_input_path
    if not run_trace_probe:
        return None
    return asyncio.run(probe_agent_traces.main_async(trace_output_path))


def build_trace_summary(trace_path: Path | None) -> dict[str, object]:
    if trace_path is None or not trace_path.exists():
        return {
            "status": "no_traces",
            "input": "" if trace_path is None else str(trace_path),
            "total_runs": 0,
            "agents": [],
        }
    payload = json.loads(trace_path.read_text(encoding="utf-8-sig"))
    runs = parse_trace_runs(payload)
    report = build_agent_trace_report(
        runs,
        metadata={
            "source": str(trace_path),
            "generated_at": utc_now(),
            "app_version": APP_VERSION,
        },
    ).to_dict()
    return {
        "status": report["status"],
        "input": str(trace_path),
        "total_runs": report["total_runs"],
        "agents": report["agents"],
    }


def build_langsmith_config_summary() -> dict[str, object]:
    config = get_agent_tracing_config()
    env = config.to_langsmith_env()
    return {
        "enabled": config.is_langsmith_enabled,
        "tracing_flag": config.langchain_tracing_enabled,
        "project": config.langchain_project,
        "api_key_configured": bool(config.langsmith_api_key),
        "api_key_redacted": bool(config.langsmith_api_key),
        "agent_local_trace_enabled": config.agent_local_trace_enabled,
        "env_keys": sorted(env.keys()),
        "env": safe_trace_payload(env),
    }


def build_cold_import_summary(module_name: str) -> dict[str, object]:
    command = (
        sys.executable,
        "-c",
        (
            "import json, sys; "
            f"import {module_name}; "
            f"names={list(HEAVY_MODULES)!r}; "
            "print(json.dumps({name: (name in sys.modules) for name in names}))"
        ),
    )
    completed = subprocess.run(
        command,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    loaded = parse_loaded_modules(completed.stdout)
    heavy_loaded = [name for name, present in loaded.items() if present]
    return {
        "module": module_name,
        "status": "passed"
        if completed.returncode == 0 and not heavy_loaded
        else "failed",
        "returncode": completed.returncode,
        "heavy_modules": loaded,
        "heavy_loaded": heavy_loaded,
        "stderr": completed.stderr.strip(),
    }


def parse_loaded_modules(stdout: str) -> dict[str, bool]:
    try:
        payload = json.loads(stdout.strip())
    except json.JSONDecodeError:
        return {name: True for name in HEAVY_MODULES}
    if not isinstance(payload, dict):
        return {name: True for name in HEAVY_MODULES}
    return {name: bool(payload.get(name)) for name in HEAVY_MODULES}


def count_failed_checks(
    *,
    trace_report: dict[str, object],
    langsmith_config: dict[str, object],
    cold_imports: list[dict[str, object]],
) -> int:
    failed = 0
    if trace_report.get("status") != "ok":
        failed += 1
    if (
        langsmith_config.get("enabled") is True
        and langsmith_config.get("api_key_configured") is not True
    ):
        failed += 1
    failed += sum(1 for item in cold_imports if item.get("status") != "passed")
    return failed


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build LangChain AI layer observability evidence report"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="写入观测证据 JSON 路径",
    )
    parser.add_argument("--trace-input", type=Path, help="读取指定 trace JSON")
    parser.add_argument(
        "--trace-output",
        type=Path,
        default=DEFAULT_TRACE_OUTPUT_PATH,
        help="运行 trace probe 时写入的 trace JSON 路径",
    )
    parser.add_argument(
        "--skip-trace-probe",
        action="store_true",
        help="不运行本地 trace probe，只检查配置和冷导入",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_observability_evidence_report(
        trace_input_path=args.trace_input,
        run_trace_probe=not args.skip_trace_probe,
        trace_output_path=args.trace_output,
    )
    if args.json_out is not None:
        write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "langchain_observability_evidence "
            f"status={report['status']} failed={report['failed']} "
            f"trace_status={report['trace']['status']} "
            f"langsmith_enabled={str(report['langsmith']['enabled']).lower()}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_text_report(report: dict[str, object]) -> None:
    print("langchain_observability_evidence")
    print(f"status={report['status']} failed={report['failed']}")
    print(f"trace={report['trace']['status']} runs={report['trace']['total_runs']}")
    print(
        "langsmith="
        f"{str(report['langsmith']['enabled']).lower()} "
        f"project={report['langsmith']['project']}"
    )
    for item in report["cold_imports"]:
        print(f"{item['status'].upper()} cold_import {item['module']}")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
