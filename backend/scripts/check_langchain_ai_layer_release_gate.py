"""LangChain AI 应用层发布门禁。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_AGENT_EVAL_PATH = ROOT_DIR / "reports" / "agent-eval" / "latest.json"
DEFAULT_REPLY_PROBE_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "customer-reply-replay-probe-latest.json"
)
DEFAULT_REPLY_EVAL_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "latest-with-reply-replay.json"
)
DEFAULT_REAL_REPLAY_FIXTURE_PATH = (
    ROOT_DIR / "tests" / "fixtures" / "customer_real_replay_sample.json"
)
DEFAULT_REAL_REPLAY_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-conversation-replay-latest.json"
)
DEFAULT_REAL_REPLIES_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-conversation-replies-latest.json"
)
DEFAULT_REAL_AGENT_EVAL_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "latest-with-real-conversation-replay.json"
)
DEFAULT_REAL_COVERAGE_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-conversation-replay-coverage.json"
)
DEFAULT_REAL_POOL_MANIFEST_PATH = (
    ROOT_DIR / "tests" / "fixtures" / "customer_real_replay_pool_manifest_sample.json"
)
DEFAULT_REAL_POOL_REPORT_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-conversation-replay-pool.json"
)
DEFAULT_REAL_INTAKE_READINESS_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-conversation-replay-intake.json"
)
DEFAULT_OBSERVABILITY_EVIDENCE_PATH = (
    ROOT_DIR / "reports" / "agent-traces" / "langchain-observability-evidence.json"
)
DEFAULT_LANGSMITH_RUNTIME_CONFIG_PATH = (
    ROOT_DIR / "reports" / "agent-traces" / "langsmith-runtime-config.json"
)
DEFAULT_CAPACITY_PATH = (
    ROOT_DIR / "reports" / "agent-traces" / "langchain-ai-layer-capacity.json"
)
DEFAULT_RAG_MATRIX_PATH = ROOT_DIR / "reports" / "rag-eval" / "latest-matrix.json"
DEFAULT_PRODUCTION_SMOKE_PATH = (
    ROOT_DIR / "reports" / "smoke" / "langchain-prod-smoke-{timestamp}.json"
)
DEFAULT_PRODUCTION_CALLBACK_PATH = (
    ROOT_DIR
    / "reports"
    / "wecom-employee-agent"
    / "langchain-prod-callback-{timestamp}.json"
)
DEFAULT_PRODUCTION_BASE_URL = "https://yunxifood.cn"
OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"


@dataclass(frozen=True)
class GateStep:
    name: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class GateStepResult:
    name: str
    command: tuple[str, ...]
    returncode: int
    stdout: str | None
    stderr: str | None

    @property
    def passed(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "command": list(self.command),
            "passed": self.passed,
            "returncode": self.returncode,
            "stdout": (self.stdout or "").strip(),
            "stderr": (self.stderr or "").strip(),
        }


def build_gate_steps(
    *,
    include_rag_matrix: bool = False,
    include_real_replay: bool = False,
    include_real_replay_coverage: bool = False,
    include_real_replay_pool: bool = False,
    include_real_replay_intake_readiness: bool = False,
    require_real_replay_pool: bool = False,
    include_observability_evidence: bool = False,
    include_production_runtime_capacity: bool = False,
    include_production_smoke: bool = False,
    production_base_url: str = DEFAULT_PRODUCTION_BASE_URL,
    agent_eval_path: Path = DEFAULT_AGENT_EVAL_PATH,
    reply_probe_path: Path = DEFAULT_REPLY_PROBE_PATH,
    reply_eval_path: Path = DEFAULT_REPLY_EVAL_PATH,
    real_replay_fixture_path: Path = DEFAULT_REAL_REPLAY_FIXTURE_PATH,
    real_replay_path: Path = DEFAULT_REAL_REPLAY_PATH,
    real_replies_path: Path = DEFAULT_REAL_REPLIES_PATH,
    real_agent_eval_path: Path = DEFAULT_REAL_AGENT_EVAL_PATH,
    real_coverage_path: Path = DEFAULT_REAL_COVERAGE_PATH,
    real_pool_manifest_path: Path = DEFAULT_REAL_POOL_MANIFEST_PATH,
    real_pool_report_path: Path = DEFAULT_REAL_POOL_REPORT_PATH,
    real_intake_readiness_path: Path = DEFAULT_REAL_INTAKE_READINESS_PATH,
    observability_evidence_path: Path = DEFAULT_OBSERVABILITY_EVIDENCE_PATH,
    langsmith_runtime_config_path: Path = DEFAULT_LANGSMITH_RUNTIME_CONFIG_PATH,
    capacity_path: Path = DEFAULT_CAPACITY_PATH,
    real_replay_min_per_scenario: int = 5,
    rag_matrix_path: Path = DEFAULT_RAG_MATRIX_PATH,
    production_smoke_path: Path = DEFAULT_PRODUCTION_SMOKE_PATH,
    production_callback_path: Path = DEFAULT_PRODUCTION_CALLBACK_PATH,
) -> tuple[GateStep, ...]:
    steps = [
        GateStep(
            name="agent_eval_default",
            command=(
                sys.executable,
                "scripts/report_agent_eval.py",
                "--latest",
                "--json-out",
                str(agent_eval_path),
                "--summary",
            ),
        ),
        GateStep(
            name="customer_reply_replay_probe",
            command=(
                sys.executable,
                "scripts/probe_customer_reply_replay.py",
                "--output",
                str(reply_probe_path),
            ),
        ),
        GateStep(
            name="agent_eval_with_reply_replay",
            command=(
                sys.executable,
                "scripts/report_agent_eval.py",
                "--latest",
                "--include-reply-replay",
                "--reply-replay-json",
                str(reply_probe_path),
                "--json-out",
                str(reply_eval_path),
                "--summary",
            ),
        ),
    ]
    if include_real_replay:
        steps.extend(
            [
                GateStep(
                    name="real_conversation_replay",
                    command=(
                        sys.executable,
                        "scripts/check_real_conversation_replay.py",
                        "--fixture",
                        str(real_replay_fixture_path),
                        "--json-out",
                        str(real_replay_path),
                        "--replies-json-out",
                        str(real_replies_path),
                        "--summary",
                    ),
                ),
                GateStep(
                    name="agent_eval_with_real_replay",
                    command=(
                        sys.executable,
                        "scripts/report_agent_eval.py",
                        "--latest",
                        "--include-real-replay",
                        "--real-replay-fixture",
                        str(real_replay_fixture_path),
                        "--json-out",
                        str(real_agent_eval_path),
                        "--summary",
                    ),
                ),
            ]
        )
        if include_real_replay_coverage:
            steps.append(
                GateStep(
                    name="real_conversation_replay_coverage",
                    command=(
                        sys.executable,
                        "scripts/check_real_conversation_replay_coverage.py",
                        "--fixture",
                        str(real_replay_fixture_path),
                        "--min-per-scenario",
                        str(real_replay_min_per_scenario),
                        "--json-out",
                        str(real_coverage_path),
                        "--summary",
                    ),
                )
            )
    if include_real_replay_pool:
        pool_command = [
            sys.executable,
            "scripts/check_real_conversation_replay_pool.py",
            "--manifest",
            str(real_pool_manifest_path),
            "--json-out",
            str(real_pool_report_path),
            "--summary",
        ]
        if require_real_replay_pool:
            pool_command.append("--require-real")
        steps.append(
            GateStep(
                name="real_conversation_replay_pool",
                command=tuple(pool_command),
            )
        )
    if include_real_replay_intake_readiness:
        steps.append(
            GateStep(
                name="real_conversation_replay_intake_readiness",
                command=(
                    sys.executable,
                    "scripts/check_real_conversation_replay_intake_readiness.py",
                    "--manifest",
                    str(real_pool_manifest_path),
                    "--json-out",
                    str(real_intake_readiness_path),
                    "--summary",
                ),
            )
        )
    if include_observability_evidence:
        steps.extend(
            [
                GateStep(
                    name="langsmith_runtime_config",
                    command=(
                        sys.executable,
                        "scripts/check_langsmith_runtime_config.py",
                        "--json-out",
                        str(langsmith_runtime_config_path),
                        "--summary",
                    ),
                ),
                GateStep(
                    name="langchain_observability_evidence",
                    command=(
                        sys.executable,
                        "scripts/report_langchain_observability_evidence.py",
                        "--json-out",
                        str(observability_evidence_path),
                        "--summary",
                    ),
                ),
            ]
        )
    if include_production_runtime_capacity:
        steps.append(
            GateStep(
                name="production_runtime_capacity",
                command=(
                    sys.executable,
                    "scripts/check_langchain_ai_layer_capacity.py",
                    "--include-production-runtime",
                    "--json-out",
                    str(capacity_path),
                    "--summary",
                ),
            )
        )
    if include_rag_matrix:
        steps.append(
            GateStep(
                name="rag_eval_matrix",
                command=(
                    sys.executable,
                    "scripts/report_retrieval_eval_matrix.py",
                    "--db",
                    "data/bot.db",
                    "--fixture",
                    "tests/fixtures/customer_rag_golden_cases.json",
                    "--k",
                    "5",
                    "--json-out",
                    str(rag_matrix_path),
                ),
            )
        )
    if include_production_smoke:
        steps.extend(
            [
                GateStep(
                    name="production_smoke",
                    command=(
                        sys.executable,
                        "scripts/smoke_test.py",
                        "--base-url",
                        production_base_url,
                        "--http-only",
                        "--json",
                        "--output",
                        str(production_smoke_path),
                    ),
                ),
                GateStep(
                    name="production_employee_callback_probe",
                    command=(
                        sys.executable,
                        "scripts/check_wecom_employee_agent_callback.py",
                        "--base-url",
                        production_base_url,
                        "--json",
                        "--output",
                        str(production_callback_path),
                    ),
                ),
            ]
        )
    return tuple(steps)


def run_gate_steps(steps: tuple[GateStep, ...]) -> tuple[GateStepResult, ...]:
    results: list[GateStepResult] = []
    for step in steps:
        completed = subprocess.run(
            step.command,
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        result = GateStepResult(
            name=step.name,
            command=step.command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        results.append(result)
        if not result.passed:
            break
    return tuple(results)


def build_gate_report(
    results: tuple[GateStepResult, ...],
    *,
    include_rag_matrix: bool,
    include_real_replay: bool,
    include_real_replay_coverage: bool,
    include_real_replay_pool: bool = False,
    include_real_replay_intake_readiness: bool = False,
    require_real_replay_pool: bool,
    include_observability_evidence: bool,
    include_production_runtime_capacity: bool,
    include_production_smoke: bool,
    production_base_url: str,
    agent_eval_path: Path = DEFAULT_AGENT_EVAL_PATH,
    reply_eval_path: Path = DEFAULT_REPLY_EVAL_PATH,
    real_replay_path: Path = DEFAULT_REAL_REPLAY_PATH,
    real_agent_eval_path: Path = DEFAULT_REAL_AGENT_EVAL_PATH,
    real_coverage_path: Path = DEFAULT_REAL_COVERAGE_PATH,
    real_pool_report_path: Path = DEFAULT_REAL_POOL_REPORT_PATH,
    real_intake_readiness_path: Path = DEFAULT_REAL_INTAKE_READINESS_PATH,
    observability_evidence_path: Path = DEFAULT_OBSERVABILITY_EVIDENCE_PATH,
    langsmith_runtime_config_path: Path = DEFAULT_LANGSMITH_RUNTIME_CONFIG_PATH,
    capacity_path: Path = DEFAULT_CAPACITY_PATH,
    rag_matrix_path: Path = DEFAULT_RAG_MATRIX_PATH,
    production_smoke_path: Path = DEFAULT_PRODUCTION_SMOKE_PATH,
    production_callback_path: Path = DEFAULT_PRODUCTION_CALLBACK_PATH,
) -> dict[str, object]:
    failed = sum(1 for result in results if not result.passed)
    return {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": _utc_now(),
        "include_rag_matrix": include_rag_matrix,
        "include_real_replay": include_real_replay,
        "include_real_replay_coverage": include_real_replay_coverage,
        "include_real_replay_pool": include_real_replay_pool,
        "include_real_replay_intake_readiness": include_real_replay_intake_readiness,
        "require_real_replay_pool": require_real_replay_pool,
        "include_observability_evidence": include_observability_evidence,
        "include_production_runtime_capacity": include_production_runtime_capacity,
        "include_production_smoke": include_production_smoke,
        "production_base_url": production_base_url
        if include_production_smoke
        else None,
        "total": len(results),
        "failed": failed,
        "release_summary": build_release_summary(
            include_rag_matrix=include_rag_matrix,
            include_real_replay=include_real_replay,
            include_real_replay_coverage=include_real_replay_coverage,
            include_real_replay_pool=include_real_replay_pool,
            include_real_replay_intake_readiness=include_real_replay_intake_readiness,
            include_observability_evidence=include_observability_evidence,
            include_production_runtime_capacity=include_production_runtime_capacity,
            include_production_smoke=include_production_smoke,
            agent_eval_path=agent_eval_path,
            reply_eval_path=reply_eval_path,
            real_replay_path=real_replay_path,
            real_agent_eval_path=real_agent_eval_path,
            real_coverage_path=real_coverage_path,
            real_pool_report_path=real_pool_report_path,
            real_intake_readiness_path=real_intake_readiness_path,
            observability_evidence_path=observability_evidence_path,
            langsmith_runtime_config_path=langsmith_runtime_config_path,
            capacity_path=capacity_path,
            rag_matrix_path=rag_matrix_path,
            production_smoke_path=production_smoke_path,
            production_callback_path=production_callback_path,
        ),
        "steps": [result.to_dict() for result in results],
    }


def build_release_summary(
    *,
    include_rag_matrix: bool,
    include_real_replay: bool,
    include_real_replay_coverage: bool,
    include_real_replay_pool: bool = False,
    include_real_replay_intake_readiness: bool = False,
    include_observability_evidence: bool = False,
    include_production_runtime_capacity: bool = False,
    include_production_smoke: bool,
    agent_eval_path: Path = DEFAULT_AGENT_EVAL_PATH,
    reply_eval_path: Path = DEFAULT_REPLY_EVAL_PATH,
    real_replay_path: Path = DEFAULT_REAL_REPLAY_PATH,
    real_agent_eval_path: Path = DEFAULT_REAL_AGENT_EVAL_PATH,
    real_coverage_path: Path = DEFAULT_REAL_COVERAGE_PATH,
    real_pool_report_path: Path = DEFAULT_REAL_POOL_REPORT_PATH,
    real_intake_readiness_path: Path = DEFAULT_REAL_INTAKE_READINESS_PATH,
    observability_evidence_path: Path = DEFAULT_OBSERVABILITY_EVIDENCE_PATH,
    langsmith_runtime_config_path: Path = DEFAULT_LANGSMITH_RUNTIME_CONFIG_PATH,
    capacity_path: Path = DEFAULT_CAPACITY_PATH,
    rag_matrix_path: Path = DEFAULT_RAG_MATRIX_PATH,
    production_smoke_path: Path = DEFAULT_PRODUCTION_SMOKE_PATH,
    production_callback_path: Path = DEFAULT_PRODUCTION_CALLBACK_PATH,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "agent_eval_default": summarize_agent_eval_report(
            read_json_report(agent_eval_path)
        ),
        "agent_eval_with_reply_replay": summarize_agent_eval_report(
            read_json_report(reply_eval_path)
        ),
        "real_conversation_replay": None,
        "agent_eval_with_real_replay": None,
        "real_conversation_replay_coverage": None,
        "real_conversation_replay_pool": None,
        "real_conversation_replay_intake_readiness": None,
        "langchain_observability_evidence": None,
        "langsmith_runtime_config": None,
        "langchain_ai_layer_capacity": None,
        "rag_eval_matrix": None,
        "production_smoke": None,
        "production_employee_callback_probe": None,
    }
    if include_real_replay:
        summary["real_conversation_replay"] = summarize_agent_eval_report(
            read_json_report(real_replay_path)
        )
        summary["agent_eval_with_real_replay"] = summarize_agent_eval_report(
            read_json_report(real_agent_eval_path)
        )
        if include_real_replay_coverage:
            summary["real_conversation_replay_coverage"] = summarize_coverage_report(
                read_json_report(real_coverage_path)
            )
    if include_real_replay_pool:
        summary["real_conversation_replay_pool"] = summarize_replay_pool_report(
            read_json_report(real_pool_report_path)
        )
    if include_real_replay_intake_readiness:
        summary["real_conversation_replay_intake_readiness"] = (
            summarize_replay_intake_readiness_report(
                read_json_report(real_intake_readiness_path)
            )
        )
    if include_observability_evidence:
        summary["langsmith_runtime_config"] = summarize_langsmith_runtime_config_report(
            read_json_report(langsmith_runtime_config_path)
        )
        summary["langchain_observability_evidence"] = summarize_observability_report(
            read_json_report(observability_evidence_path)
        )
    if include_production_runtime_capacity:
        summary["langchain_ai_layer_capacity"] = summarize_capacity_report(
            read_json_report(capacity_path)
        )
    if include_rag_matrix:
        summary["rag_eval_matrix"] = summarize_rag_matrix_report(
            read_json_report(rag_matrix_path)
        )
    if include_production_smoke:
        summary["production_smoke"] = summarize_smoke_report(
            read_json_report(production_smoke_path)
        )
        summary["production_employee_callback_probe"] = summarize_callback_report(
            read_json_report(production_callback_path)
        )
    return summary


def summarize_agent_eval_report(report: dict[str, object]) -> dict[str, object]:
    metadata = _dict_value(report, "metadata")
    return {
        "status": report.get("status", "missing"),
        "total": report.get("total", 0),
        "failed": report.get("failed", 0),
        "pass_rate": report.get("pass_rate", 0.0),
        "app_version": metadata.get("app_version", ""),
        "agent_totals": report.get("agent_totals", []),
        "sensitive_scenarios": report.get("sensitive_scenarios", []),
    }


def summarize_rag_matrix_report(report: dict[str, object]) -> dict[str, object]:
    metadata = _dict_value(report, "metadata")
    result_summaries = []
    for result in _list_value(report, "results"):
        if not isinstance(result, dict):
            continue
        result_summaries.append(
            {
                "name": result.get("name", ""),
                "recall_at_k": result.get("recall_at_k", 0.0),
                "mrr": result.get("mrr", 0.0),
                "evaluable": result.get("evaluable", 0),
            }
        )
    return {
        "status": "available" if report else "missing",
        "corpus_size": metadata.get("corpus_size", 0),
        "total_cases": metadata.get("total_cases", 0),
        "k": metadata.get("k", 0),
        "best": report.get("best", {}),
        "results": result_summaries,
    }


def summarize_smoke_report(report: dict[str, object]) -> dict[str, object]:
    metadata = _dict_value(report, "metadata")
    return {
        "status": report.get("status", "missing"),
        "total": report.get("total", 0),
        "failed": report.get("failed", 0),
        "server_base_url": metadata.get("server_base_url", ""),
        "app_version": metadata.get("app_version", ""),
        "failed_names": report.get("failed_names", []),
        "checks": summarize_named_results(report),
    }


def summarize_callback_report(report: dict[str, object]) -> dict[str, object]:
    metadata = _dict_value(report, "metadata")
    return {
        "status": report.get("status", "missing"),
        "total": report.get("total", 0),
        "failed": report.get("failed", 0),
        "base_url": metadata.get("base_url", ""),
        "app_version": metadata.get("app_version", ""),
        "failed_names": report.get("failed_names", []),
    }


def summarize_coverage_report(report: dict[str, object]) -> dict[str, object]:
    return {
        "status": report.get("status", "missing"),
        "total": report.get("total", 0),
        "failed": report.get("failed", 0),
        "min_per_scenario": report.get("min_per_scenario", 0),
        "replay_total": report.get("replay_total", 0),
        "replay_failed": report.get("replay_failed", 0),
        "scenario_coverage": report.get("scenario_coverage", []),
    }


def summarize_replay_pool_report(report: dict[str, object]) -> dict[str, object]:
    return {
        "status": report.get("status", "missing"),
        "total": report.get("total", 0),
        "failed": report.get("failed", 0),
        "real_entries": report.get("real_entries", 0),
        "synthetic_entries": report.get("synthetic_entries", 0),
        "real_pool_ready": report.get("real_pool_ready", False),
        "manifest": report.get("manifest", ""),
    }


def summarize_replay_intake_readiness_report(
    report: dict[str, object],
) -> dict[str, object]:
    pool = _dict_value(report, "pool")
    return {
        "status": report.get("status", "missing"),
        "failed": report.get("failed", 0),
        "real_sample_ready": report.get("real_sample_ready", False),
        "missing_actions": report.get("missing_actions", []),
        "pool_status": pool.get("status", "missing"),
        "real_entries": pool.get("real_entries", 0),
        "synthetic_entries": pool.get("synthetic_entries", 0),
    }


def summarize_observability_report(report: dict[str, object]) -> dict[str, object]:
    trace = _dict_value(report, "trace")
    langsmith = _dict_value(report, "langsmith")
    return {
        "status": report.get("status", "missing"),
        "failed": report.get("failed", 0),
        "trace_status": trace.get("status", "missing"),
        "trace_total_runs": trace.get("total_runs", 0),
        "langsmith_enabled": langsmith.get("enabled", False),
        "langsmith_project": langsmith.get("project", ""),
        "cold_imports": report.get("cold_imports", []),
    }


def summarize_langsmith_runtime_config_report(
    report: dict[str, object],
) -> dict[str, object]:
    runtime = _dict_value(report, "runtime")
    metadata_redaction = _dict_value(report, "metadata_redaction")
    return {
        "status": report.get("status", "missing"),
        "enabled": runtime.get("enabled", False),
        "safe_to_enable": runtime.get("safe_to_enable", False),
        "project": runtime.get("project", ""),
        "api_key_configured": runtime.get("api_key_configured", False),
        "missing": runtime.get("missing", []),
        "metadata_redaction_status": metadata_redaction.get("status", "missing"),
    }


def summarize_capacity_report(report: dict[str, object]) -> dict[str, object]:
    trace_probe = _dict_value(report, "trace_probe")
    production_runtime = _dict_value(report, "production_runtime")
    return {
        "status": report.get("status", "missing"),
        "failed": report.get("failed", 0),
        "trace_latency_ms": trace_probe.get("latency_ms", 0),
        "payload_bytes": trace_probe.get("payload_bytes", 0),
        "production_runtime_status": production_runtime.get("status", "missing"),
        "service_active": production_runtime.get("service_active", False),
        "version": production_runtime.get("version", ""),
        "health_version": production_runtime.get("health_version", ""),
        "ready_version": production_runtime.get("ready_version", ""),
        "rss_mb": production_runtime.get("rss_mb", 0.0),
        "mem_available_mb": production_runtime.get("mem_available_mb", 0.0),
        "load1": production_runtime.get("load1", 0.0),
    }


def summarize_named_results(report: dict[str, object]) -> list[dict[str, object]]:
    summaries = []
    for result in _list_value(report, "results"):
        if not isinstance(result, dict):
            continue
        summaries.append(
            {
                "name": result.get("name", ""),
                "passed": result.get("passed", False),
                "detail": result.get("detail", ""),
            }
        )
    return summaries


def read_json_report(path: Path) -> dict[str, object]:
    resolved_path = resolve_existing_report_path(path)
    if resolved_path is None:
        return {}
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_existing_report_path(path: Path) -> Path | None:
    if OUTPUT_TIMESTAMP_PLACEHOLDER not in str(path):
        return path if path.exists() else None
    glob_pattern = path.name.replace(OUTPUT_TIMESTAMP_PLACEHOLDER, "*")
    candidates = [candidate for candidate in path.parent.glob(glob_pattern)]
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate.name)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LangChain AI layer release gate")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument("--json-out", type=Path, help="写入 JSON 报告路径")
    parser.add_argument(
        "--include-rag-matrix",
        action="store_true",
        help="额外运行 RAG 检索矩阵，耗时较长",
    )
    parser.add_argument(
        "--include-real-replay",
        action="store_true",
        help="额外运行脱敏真实会话 replay 契约检查和聚合 eval",
    )
    parser.add_argument(
        "--include-real-replay-coverage",
        action="store_true",
        help="额外检查脱敏真实会话 replay 的事实敏感场景覆盖率",
    )
    parser.add_argument(
        "--real-replay-fixture",
        type=Path,
        default=DEFAULT_REAL_REPLAY_FIXTURE_PATH,
        help="脱敏真实会话 replay fixture 路径",
    )
    parser.add_argument(
        "--real-replay-min-per-scenario",
        type=int,
        default=5,
        help="启用 --include-real-replay-coverage 时，每个敏感场景至少需要的 replay case 数",
    )
    parser.add_argument(
        "--include-real-replay-pool",
        action="store_true",
        help="额外检查脱敏真实会话 replay 样本池 manifest",
    )
    parser.add_argument(
        "--include-real-replay-intake-readiness",
        action="store_true",
        help="额外检查真实脱敏会话 replay 接入准备度",
    )
    parser.add_argument(
        "--real-replay-pool-manifest",
        type=Path,
        default=DEFAULT_REAL_POOL_MANIFEST_PATH,
        help="脱敏真实会话 replay 样本池 manifest 路径",
    )
    parser.add_argument(
        "--require-real-replay-pool",
        action="store_true",
        help="要求样本池至少包含一个通过门禁的真实脱敏条目",
    )
    parser.add_argument(
        "--include-observability-evidence",
        action="store_true",
        help="额外运行 LangChain AI 应用层观测证据包",
    )
    parser.add_argument(
        "--include-production-smoke",
        action="store_true",
        help="额外运行生产 /health、/ready、企微员工助手 callback 探针",
    )
    parser.add_argument(
        "--include-production-runtime-capacity",
        action="store_true",
        help="额外运行生产只读资源观测容量门禁，不做压测",
    )
    parser.add_argument(
        "--production-base-url",
        default=DEFAULT_PRODUCTION_BASE_URL,
        help="生产门禁目标服务根地址，仅在 --include-production-smoke 时使用",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    ensure_output_directories(
        include_rag_matrix=args.include_rag_matrix,
        include_real_replay=args.include_real_replay,
        include_real_replay_coverage=args.include_real_replay_coverage,
        include_real_replay_pool=args.include_real_replay_pool,
        include_real_replay_intake_readiness=args.include_real_replay_intake_readiness,
        include_observability_evidence=args.include_observability_evidence,
        include_production_runtime_capacity=args.include_production_runtime_capacity,
        include_production_smoke=args.include_production_smoke,
    )
    steps = build_gate_steps(
        include_rag_matrix=args.include_rag_matrix,
        include_real_replay=args.include_real_replay,
        include_real_replay_coverage=args.include_real_replay_coverage,
        include_real_replay_pool=args.include_real_replay_pool,
        include_real_replay_intake_readiness=args.include_real_replay_intake_readiness,
        require_real_replay_pool=args.require_real_replay_pool,
        include_observability_evidence=args.include_observability_evidence,
        include_production_runtime_capacity=args.include_production_runtime_capacity,
        include_production_smoke=args.include_production_smoke,
        production_base_url=args.production_base_url,
        real_replay_fixture_path=args.real_replay_fixture,
        real_pool_manifest_path=args.real_replay_pool_manifest,
        real_replay_min_per_scenario=args.real_replay_min_per_scenario,
    )
    results = run_gate_steps(steps)
    report = build_gate_report(
        results,
        include_rag_matrix=args.include_rag_matrix,
        include_real_replay=args.include_real_replay,
        include_real_replay_coverage=args.include_real_replay_coverage,
        include_real_replay_pool=args.include_real_replay_pool,
        include_real_replay_intake_readiness=args.include_real_replay_intake_readiness,
        require_real_replay_pool=args.require_real_replay_pool,
        include_observability_evidence=args.include_observability_evidence,
        include_production_runtime_capacity=args.include_production_runtime_capacity,
        include_production_smoke=args.include_production_smoke,
        production_base_url=args.production_base_url,
        agent_eval_path=DEFAULT_AGENT_EVAL_PATH,
        reply_eval_path=DEFAULT_REPLY_EVAL_PATH,
        real_replay_path=DEFAULT_REAL_REPLAY_PATH,
        real_agent_eval_path=DEFAULT_REAL_AGENT_EVAL_PATH,
        real_coverage_path=DEFAULT_REAL_COVERAGE_PATH,
        real_pool_report_path=DEFAULT_REAL_POOL_REPORT_PATH,
        observability_evidence_path=DEFAULT_OBSERVABILITY_EVIDENCE_PATH,
        capacity_path=DEFAULT_CAPACITY_PATH,
        rag_matrix_path=DEFAULT_RAG_MATRIX_PATH,
        production_smoke_path=DEFAULT_PRODUCTION_SMOKE_PATH,
        production_callback_path=DEFAULT_PRODUCTION_CALLBACK_PATH,
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "langchain_ai_layer_release_gate "
            f"status={report['status']} total={report['total']} failed={report['failed']}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def ensure_output_directories(
    *,
    include_rag_matrix: bool,
    include_real_replay: bool = False,
    include_real_replay_coverage: bool = False,
    include_real_replay_pool: bool = False,
    include_real_replay_intake_readiness: bool = False,
    include_observability_evidence: bool = False,
    include_production_runtime_capacity: bool = False,
    include_production_smoke: bool = False,
) -> None:
    DEFAULT_AGENT_EVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_REPLY_PROBE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_REPLY_EVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if include_real_replay:
        DEFAULT_REAL_REPLAY_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_REAL_REPLIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_REAL_AGENT_EVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if include_real_replay_coverage:
        DEFAULT_REAL_COVERAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if include_real_replay_pool:
        DEFAULT_REAL_POOL_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if include_real_replay_intake_readiness:
        DEFAULT_REAL_INTAKE_READINESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if include_observability_evidence:
        DEFAULT_OBSERVABILITY_EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_LANGSMITH_RUNTIME_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if include_production_runtime_capacity:
        DEFAULT_CAPACITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if include_rag_matrix:
        DEFAULT_RAG_MATRIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    if include_production_smoke:
        DEFAULT_PRODUCTION_SMOKE_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_PRODUCTION_CALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)


def print_text_report(report: dict[str, object]) -> None:
    print("langchain_ai_layer_release_gate")
    print(
        f"status={report['status']} total={report['total']} failed={report['failed']}"
    )
    for step in report["steps"]:
        mark = "PASS" if step["passed"] else "FAIL"
        print(f"{mark} {step['name']}")


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _dict_value(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _list_value(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


if __name__ == "__main__":
    raise SystemExit(main())
