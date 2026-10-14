"""LangChain AI 应用层容量门禁。"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from app.service.agents.evaluation import write_json_report  # noqa: E402
from app.service.agents.trace_report import parse_trace_runs  # noqa: E402
from scripts import probe_agent_traces  # noqa: E402
from scripts.check_langsmith_production_rollout import (  # noqa: E402
    MAX_DEFAULT_SAMPLE_RATE,
    build_langsmith_production_rollout_report,
)
from scripts.report_langchain_observability_evidence import (  # noqa: E402
    COLD_IMPORT_TARGETS,
    build_cold_import_summary,
)

DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "agent-traces" / "langchain-ai-layer-capacity.json"
)
DEFAULT_TRACE_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "agent-traces" / "langchain-capacity-trace-probe.json"
)
# 该指标包含独立 probe 进程启动和冷导入耗时，不等同于线上请求延迟。
DEFAULT_MAX_TRACE_PROBE_LATENCY_MS = 15000
DEFAULT_MAX_TRACE_PAYLOAD_BYTES = 200_000
DEFAULT_MAX_EVENTS_PER_RUN = 20
DEFAULT_PRODUCTION_SSH_TARGET = "root@47.94.102.250"
DEFAULT_PRODUCTION_SERVICE_NAME = "yunxibakebot"
DEFAULT_PRODUCTION_APP_DIR = "/opt/apps/yunxibakebot"
DEFAULT_PRODUCTION_LOCAL_BASE_URL = "http://127.0.0.1:7001"
DEFAULT_MAX_PRODUCTION_RSS_MB = 512.0
DEFAULT_MIN_PRODUCTION_MEM_AVAILABLE_MB = 128.0
DEFAULT_MAX_PRODUCTION_LOAD1 = 4.0


def build_capacity_report(
    *,
    trace_input_path: Path | None = None,
    run_trace_probe: bool = True,
    trace_output_path: Path = DEFAULT_TRACE_OUTPUT_PATH,
    max_trace_probe_latency_ms: int = DEFAULT_MAX_TRACE_PROBE_LATENCY_MS,
    max_trace_payload_bytes: int = DEFAULT_MAX_TRACE_PAYLOAD_BYTES,
    max_events_per_run: int = DEFAULT_MAX_EVENTS_PER_RUN,
    include_production_runtime: bool = False,
    production_ssh_target: str = DEFAULT_PRODUCTION_SSH_TARGET,
    max_production_rss_mb: float = DEFAULT_MAX_PRODUCTION_RSS_MB,
    min_production_mem_available_mb: float = DEFAULT_MIN_PRODUCTION_MEM_AVAILABLE_MB,
    max_production_load1: float = DEFAULT_MAX_PRODUCTION_LOAD1,
) -> dict[str, object]:
    trace_probe = build_trace_probe_metrics(
        trace_input_path=trace_input_path,
        run_trace_probe=run_trace_probe,
        trace_output_path=trace_output_path,
    )
    cold_imports = [build_cold_import_summary(target) for target in COLD_IMPORT_TARGETS]
    rollout = build_langsmith_production_rollout_report()
    production_runtime = build_production_runtime_metrics(
        include_production_runtime=include_production_runtime,
        ssh_target=production_ssh_target,
    )
    assertions = build_assertions(
        trace_probe=trace_probe,
        cold_imports=cold_imports,
        rollout=rollout,
        production_runtime=production_runtime,
        max_trace_probe_latency_ms=max_trace_probe_latency_ms,
        max_trace_payload_bytes=max_trace_payload_bytes,
        max_events_per_run=max_events_per_run,
        max_production_rss_mb=max_production_rss_mb,
        min_production_mem_available_mb=min_production_mem_available_mb,
        max_production_load1=max_production_load1,
    )
    failed = sum(1 for passed in assertions.values() if not passed)
    return {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "failed": failed,
        "thresholds": {
            "max_trace_probe_latency_ms": max_trace_probe_latency_ms,
            "max_trace_payload_bytes": max_trace_payload_bytes,
            "max_events_per_run": max_events_per_run,
            "max_langsmith_sample_rate": MAX_DEFAULT_SAMPLE_RATE,
            "max_production_rss_mb": max_production_rss_mb,
            "min_production_mem_available_mb": min_production_mem_available_mb,
            "max_production_load1": max_production_load1,
        },
        "trace_probe": trace_probe,
        "production_runtime": production_runtime,
        "cold_imports": cold_imports,
        "langsmith_rollout": {
            "status": rollout["status"],
            "enabled": rollout["rollout"]["enabled"],
            "sample_rate": rollout["rollout"]["sample_rate"],
            "max_default_sample_rate": rollout["rollout"]["max_default_sample_rate"],
        },
        "assertions": assertions,
        "missing_actions": build_missing_actions(assertions),
        "boundaries": {
            "production_load_test": False,
            "production_hot_path_changed": False,
            "external_llm_called": False,
            "langsmith_external_export": False,
            "business_database_read": False,
            "contains_sensitive_data": False,
            "production_runtime_checked": include_production_runtime,
        },
    }


def build_trace_probe_metrics(
    *,
    trace_input_path: Path | None,
    run_trace_probe: bool,
    trace_output_path: Path,
) -> dict[str, object]:
    started_at = perf_counter()
    trace_path = resolve_trace_path(
        trace_input_path=trace_input_path,
        run_trace_probe=run_trace_probe,
        trace_output_path=trace_output_path,
    )
    latency_ms = round((perf_counter() - started_at) * 1000, 2)
    if trace_path is None or not trace_path.exists():
        return {
            "status": "no_traces",
            "path": "" if trace_path is None else str(trace_path),
            "latency_ms": latency_ms,
            "payload_bytes": 0,
            "total_runs": 0,
            "total_events": 0,
            "max_events_per_run": 0,
        }
    payload_text = trace_path.read_text(encoding="utf-8-sig")
    runs = parse_trace_runs(json.loads(payload_text))
    event_counts = [len(run.trace_events) for run in runs]
    return {
        "status": "ok" if runs else "no_traces",
        "path": str(trace_path),
        "latency_ms": latency_ms,
        "payload_bytes": len(payload_text.encode("utf-8")),
        "total_runs": len(runs),
        "total_events": sum(event_counts),
        "max_events_per_run": max(event_counts, default=0),
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


def build_production_runtime_metrics(
    *,
    include_production_runtime: bool,
    ssh_target: str,
) -> dict[str, object]:
    if not include_production_runtime:
        return {
            "status": "skipped",
            "ssh_target": "",
            "service_active": False,
            "version": "",
            "health_version": "",
            "ready_version": "",
            "rss_mb": 0.0,
            "mem_available_mb": 0.0,
            "load1": 0.0,
            "threads": 0,
            "error": "",
        }
    completed = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            ssh_target,
            build_remote_runtime_probe_command(),
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return {
            "status": "failed",
            "ssh_target": ssh_target,
            "service_active": False,
            "version": "",
            "health_version": "",
            "ready_version": "",
            "rss_mb": 0.0,
            "mem_available_mb": 0.0,
            "load1": 0.0,
            "threads": 0,
            "error": (completed.stderr or completed.stdout).strip(),
        }
    payload = json.loads(completed.stdout)
    return {
        "status": "ok",
        "ssh_target": ssh_target,
        "service_active": payload["service_active"],
        "version": payload["version"],
        "health_version": payload["health_version"],
        "ready_version": payload["ready_version"],
        "rss_mb": payload["rss_mb"],
        "mem_available_mb": payload["mem_available_mb"],
        "load1": payload["load1"],
        "threads": payload["threads"],
        "error": "",
    }


def build_remote_runtime_probe_command() -> str:
    return f"""cd {DEFAULT_PRODUCTION_APP_DIR} && ./venv/bin/python - <<'PY'
import json
import subprocess
import urllib.request
from pathlib import Path

service = {DEFAULT_PRODUCTION_SERVICE_NAME!r}
base_url = {DEFAULT_PRODUCTION_LOCAL_BASE_URL!r}


def command_output(args):
    return subprocess.check_output(args, text=True).strip()


def endpoint_version(path):
    with urllib.request.urlopen(base_url + path, timeout=5) as response:
        return json.loads(response.read().decode("utf-8")).get("version", "")


pid = int(command_output(["systemctl", "show", "-p", "MainPID", "--value", service]))
status_lines = Path(f"/proc/{{pid}}/status").read_text(encoding="utf-8").splitlines()
status = dict(line.split(":", 1) for line in status_lines if ":" in line)
rss_kb = float(status.get("VmRSS", "0 kB").split()[0])
threads = int(status.get("Threads", "0").strip())
meminfo = dict(
    line.split(":", 1)
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    if ":" in line
)
mem_available_kb = float(meminfo.get("MemAvailable", "0 kB").split()[0])
load1 = float(Path("/proc/loadavg").read_text(encoding="utf-8").split()[0])
print(json.dumps({{
    "service_active": command_output(["systemctl", "is-active", service]) == "active",
    "version": Path("VERSION").read_text(encoding="utf-8").strip(),
    "health_version": endpoint_version("/health"),
    "ready_version": endpoint_version("/ready"),
    "rss_mb": round(rss_kb / 1024, 2),
    "mem_available_mb": round(mem_available_kb / 1024, 2),
    "load1": load1,
    "threads": threads,
}}, ensure_ascii=False))
PY"""


def build_assertions(
    *,
    trace_probe: dict[str, object],
    cold_imports: list[dict[str, object]],
    rollout: dict[str, object],
    production_runtime: dict[str, object],
    max_trace_probe_latency_ms: int,
    max_trace_payload_bytes: int,
    max_events_per_run: int,
    max_production_rss_mb: float,
    min_production_mem_available_mb: float,
    max_production_load1: float,
) -> dict[str, bool]:
    rollout_data = rollout["rollout"]
    production_checked = production_runtime["status"] != "skipped"
    return {
        "trace_probe.ok": trace_probe["status"] == "ok",
        "trace_probe.latency_within_limit": (
            production_checked
            and float(trace_probe["latency_ms"]) <= max_trace_probe_latency_ms
        )
        or not production_checked,
        "trace_probe.payload_within_limit": int(trace_probe["payload_bytes"])
        <= max_trace_payload_bytes,
        "trace_probe.events_within_limit": int(trace_probe["max_events_per_run"])
        <= max_events_per_run,
        "cold_imports.passed": all(
            item.get("status") == "passed" for item in cold_imports
        ),
        "langsmith_rollout.closed_by_default": rollout_data["enabled"] is False
        and rollout_data["sample_rate"] == 0.0,
        "langsmith_rollout.sample_rate_within_limit": float(rollout_data["sample_rate"])
        <= MAX_DEFAULT_SAMPLE_RATE,
        "langsmith_rollout.passed": rollout["status"] == "passed",
        "production_runtime.ok": not production_checked
        or production_runtime["status"] == "ok",
        "production_runtime.service_active": not production_checked
        or production_runtime["service_active"] is True,
        "production_runtime.version_matches": not production_checked
        or (
            production_runtime["version"] == APP_VERSION
            and production_runtime["health_version"] == APP_VERSION
            and production_runtime["ready_version"] == APP_VERSION
        ),
        "production_runtime.rss_within_limit": not production_checked
        or float(production_runtime["rss_mb"]) <= max_production_rss_mb,
        "production_runtime.mem_available_within_limit": not production_checked
        or float(production_runtime["mem_available_mb"])
        >= min_production_mem_available_mb,
        "production_runtime.load_within_limit": not production_checked
        or float(production_runtime["load1"]) <= max_production_load1,
    }


def build_missing_actions(assertions: dict[str, bool]) -> list[str]:
    actions = []
    if not assertions["trace_probe.ok"]:
        actions.append("fix_agent_trace_probe_before_capacity_gate")
    if not assertions["trace_probe.latency_within_limit"]:
        actions.append("reduce_langchain_graph_probe_latency")
    if not assertions["trace_probe.payload_within_limit"]:
        actions.append("reduce_trace_payload_size_or_redaction_scope")
    if not assertions["trace_probe.events_within_limit"]:
        actions.append("inspect_agent_graph_event_count_growth")
    if not assertions["cold_imports.passed"]:
        actions.append("fix_heavy_import_before_production_rollout")
    if not assertions["langsmith_rollout.closed_by_default"]:
        actions.append("keep_langsmith_external_export_disabled_by_default")
    if not assertions["langsmith_rollout.sample_rate_within_limit"]:
        actions.append("lower_langsmith_sample_rate_to_safe_default")
    if not assertions["production_runtime.ok"]:
        actions.append("fix_production_runtime_probe_or_ssh_access")
    if not assertions["production_runtime.service_active"]:
        actions.append("restart_or_inspect_production_service")
    if not assertions["production_runtime.version_matches"]:
        actions.append("sync_production_runtime_version_before_release")
    if not assertions["production_runtime.rss_within_limit"]:
        actions.append("inspect_langchain_runtime_memory_growth")
    if not assertions["production_runtime.mem_available_within_limit"]:
        actions.append("free_or_expand_production_memory_before_rollout")
    if not assertions["production_runtime.load_within_limit"]:
        actions.append("inspect_production_cpu_load_before_rollout")
    return actions


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check LangChain AI layer capacity and cost guardrails"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="写入容量门禁 JSON 路径",
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
        help="不运行 trace probe，只检查冷导入和 LangSmith 默认状态",
    )
    parser.add_argument(
        "--include-production-runtime",
        action="store_true",
        help="通过 SSH 读取生产服务只读资源指标；不做压测",
    )
    parser.add_argument(
        "--production-ssh-target",
        default=DEFAULT_PRODUCTION_SSH_TARGET,
        help="生产 SSH 目标",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_capacity_report(
        trace_input_path=args.trace_input,
        run_trace_probe=not args.skip_trace_probe,
        trace_output_path=args.trace_output,
        include_production_runtime=args.include_production_runtime,
        production_ssh_target=args.production_ssh_target,
    )
    if args.json_out is not None:
        write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "langchain_ai_layer_capacity "
            f"status={report['status']} failed={report['failed']} "
            f"trace_latency_ms={report['trace_probe']['latency_ms']} "
            f"payload_bytes={report['trace_probe']['payload_bytes']} "
            f"production_runtime={report['production_runtime']['status']}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_text_report(report: dict[str, object]) -> None:
    trace_probe = report["trace_probe"]
    print("langchain_ai_layer_capacity")
    print(
        f"status={report['status']} failed={report['failed']} "
        f"trace_latency_ms={trace_probe['latency_ms']} "
        f"payload_bytes={trace_probe['payload_bytes']} "
        f"production_runtime={report['production_runtime']['status']}"
    )
    for action in report["missing_actions"]:
        print(f"NEXT {action}")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
