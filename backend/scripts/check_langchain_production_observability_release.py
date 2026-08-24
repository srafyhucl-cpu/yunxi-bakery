"""检查 LangChain 生产观测发布证据是否可作为上线收口。"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
VERSION_PATH = ROOT_DIR / "VERSION"
DEFAULT_RELEASE_REPORT_PATH = (
    ROOT_DIR
    / "reports"
    / "agent-eval"
    / "langchain-ai-layer-release-gate-with-production-observability-latest.json"
)
HEALTH_CHECK_NAME = "健康检查接口"
READY_CHECK_NAME = "就绪检查接口"
REQUIRED_PRODUCTION_CHECK_NAMES = (HEALTH_CHECK_NAME, READY_CHECK_NAME)


@dataclass(frozen=True)
class ReleaseFinding:
    code: str
    message: str
    detail: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
        }


def build_production_observability_release_report(
    release_report_path: Path,
    *,
    expected_version: str | None = None,
) -> dict[str, object]:
    expected_app_version = expected_version or read_expected_version()
    release_report = read_json_report(release_report_path)
    findings = collect_release_findings(
        release_report,
        expected_app_version=expected_app_version,
    )
    release_summary = dict_value(release_report, "release_summary")
    production_smoke = dict_value(release_summary, "production_smoke")
    callback_probe = dict_value(
        release_summary,
        "production_employee_callback_probe",
    )
    observability = dict_value(
        release_summary,
        "langchain_observability_evidence",
    )
    capacity = dict_value(release_summary, "langchain_ai_layer_capacity")
    production_versions = extract_production_endpoint_versions(production_smoke)
    callback_failed_names = list_value(callback_probe, "failed_names")
    langsmith_enabled = observability.get("langsmith_enabled")
    return {
        "status": "passed" if not findings else "failed",
        "generated_at": utc_now(),
        "release_report": str(release_report_path),
        "expected_app_version": expected_app_version,
        "release_gate_status": release_report.get("status", "missing"),
        "failed": len(findings),
        "findings": [finding.to_dict() for finding in findings],
        "production": {
            "smoke_status": production_smoke.get("status", "missing"),
            "smoke_failed": production_smoke.get("failed", 0),
            "callback_status": callback_probe.get("status", "missing"),
            "callback_failed": callback_probe.get("failed", 0),
            "callback_failed_names": callback_failed_names,
            "endpoint_versions": production_versions,
            "summary_app_version": production_smoke.get("app_version", ""),
            "callback_app_version": callback_probe.get("app_version", ""),
        },
        "observability": {
            "status": observability.get("status", "missing"),
            "failed": observability.get("failed", 0),
            "trace_status": observability.get("trace_status", "missing"),
            "trace_total_runs": observability.get("trace_total_runs", 0),
            "langsmith_enabled": langsmith_enabled,
            "langsmith_enabled_explicit": "langsmith_enabled" in observability,
        },
        "capacity": {
            "status": capacity.get("status", "missing"),
            "failed": capacity.get("failed", 0),
            "production_runtime_status": capacity.get(
                "production_runtime_status", "missing"
            ),
            "service_active": capacity.get("service_active", False),
            "version": capacity.get("version", ""),
            "health_version": capacity.get("health_version", ""),
            "ready_version": capacity.get("ready_version", ""),
            "rss_mb": capacity.get("rss_mb", 0.0),
            "mem_available_mb": capacity.get("mem_available_mb", 0.0),
            "load1": capacity.get("load1", 0.0),
        },
    }


def collect_release_findings(
    release_report: dict[str, object],
    *,
    expected_app_version: str,
) -> list[ReleaseFinding]:
    findings: list[ReleaseFinding] = []
    if not release_report:
        return [
            ReleaseFinding(
                "release_report_missing",
                "未读取到 LangChain 生产观测 release gate 报告。",
                {},
            )
        ]
    if release_report.get("status") != "passed":
        findings.append(
            ReleaseFinding(
                "release_gate.failed",
                "release gate 顶层状态不是 passed。",
                {
                    "status": release_report.get("status", "missing"),
                    "failed": release_report.get("failed", 0),
                },
            )
        )
    release_summary = dict_value(release_report, "release_summary")
    production_smoke = dict_value(release_summary, "production_smoke")
    callback_probe = dict_value(
        release_summary,
        "production_employee_callback_probe",
    )
    observability = dict_value(
        release_summary,
        "langchain_observability_evidence",
    )
    capacity = dict_value(release_summary, "langchain_ai_layer_capacity")
    findings.extend(check_production_smoke(production_smoke))
    findings.extend(check_callback_probe(callback_probe))
    findings.extend(check_observability_evidence(observability))
    findings.extend(
        check_capacity_evidence(
            capacity,
            expected_app_version=expected_app_version,
        )
    )
    findings.extend(
        check_production_versions(
            production_smoke,
            expected_app_version=expected_app_version,
        )
    )
    return findings


def check_capacity_evidence(
    capacity: dict[str, object],
    *,
    expected_app_version: str,
) -> list[ReleaseFinding]:
    findings: list[ReleaseFinding] = []
    if not capacity:
        return [
            ReleaseFinding(
                "capacity_evidence.missing",
                "release summary 缺少 langchain_ai_layer_capacity。",
                {},
            )
        ]
    if capacity.get("status") != "passed" or capacity.get("failed") != 0:
        findings.append(
            ReleaseFinding(
                "capacity_evidence.failed",
                "LangChain AI 层容量门禁未通过。",
                {
                    "status": capacity.get("status", "missing"),
                    "failed": capacity.get("failed", 0),
                },
            )
        )
    if capacity.get("production_runtime_status") != "ok":
        findings.append(
            ReleaseFinding(
                "capacity_production_runtime.failed",
                "生产只读资源观测未通过。",
                {
                    "production_runtime_status": capacity.get(
                        "production_runtime_status", "missing"
                    ),
                    "service_active": capacity.get("service_active", False),
                },
            )
        )
    if capacity.get("service_active") is not True:
        findings.append(
            ReleaseFinding(
                "capacity_service.inactive",
                "容量报告显示生产服务不是 active。",
                {"service_active": capacity.get("service_active", False)},
            )
        )
    version_fields = {
        "version": capacity.get("version", ""),
        "health_version": capacity.get("health_version", ""),
        "ready_version": capacity.get("ready_version", ""),
    }
    mismatched_versions = {
        name: version
        for name, version in version_fields.items()
        if version != expected_app_version
    }
    if mismatched_versions:
        findings.append(
            ReleaseFinding(
                "capacity_version_mismatch",
                "容量报告中的生产版本与本地目标版本不一致。",
                {
                    "expected_app_version": expected_app_version,
                    "versions": version_fields,
                    "mismatched_versions": mismatched_versions,
                },
            )
        )
    return findings


def check_production_smoke(
    production_smoke: dict[str, object],
) -> list[ReleaseFinding]:
    if not production_smoke:
        return [
            ReleaseFinding(
                "production_smoke.missing",
                "release summary 缺少 production_smoke。",
                {},
            )
        ]
    if (
        production_smoke.get("status") == "passed"
        and production_smoke.get("failed") == 0
    ):
        return []
    return [
        ReleaseFinding(
            "production_smoke.failed",
            "生产 smoke 未通过。",
            {
                "status": production_smoke.get("status", "missing"),
                "failed": production_smoke.get("failed", 0),
                "failed_names": list_value(production_smoke, "failed_names"),
            },
        )
    ]


def check_callback_probe(
    callback_probe: dict[str, object],
) -> list[ReleaseFinding]:
    if not callback_probe:
        return [
            ReleaseFinding(
                "production_callback.missing",
                "release summary 缺少 production_employee_callback_probe。",
                {},
            )
        ]
    if callback_probe.get("status") == "passed" and callback_probe.get("failed") == 0:
        return []
    return [
        ReleaseFinding(
            "production_callback.failed",
            "生产企微员工助手 callback probe 未通过。",
            {
                "status": callback_probe.get("status", "missing"),
                "failed": callback_probe.get("failed", 0),
                "failed_names": list_value(callback_probe, "failed_names"),
            },
        )
    ]


def check_observability_evidence(
    observability: dict[str, object],
) -> list[ReleaseFinding]:
    findings: list[ReleaseFinding] = []
    if not observability:
        return [
            ReleaseFinding(
                "observability_evidence.missing",
                "release summary 缺少 langchain_observability_evidence。",
                {},
            )
        ]
    if observability.get("status") != "passed" or observability.get("failed") != 0:
        findings.append(
            ReleaseFinding(
                "observability_evidence.failed",
                "LangChain 观测证据包未通过。",
                {
                    "status": observability.get("status", "missing"),
                    "failed": observability.get("failed", 0),
                },
            )
        )
    if observability.get("trace_status") != "ok":
        findings.append(
            ReleaseFinding(
                "observability_trace.failed",
                "观测证据包没有可用 trace。",
                {
                    "trace_status": observability.get("trace_status", "missing"),
                    "trace_total_runs": observability.get("trace_total_runs", 0),
                },
            )
        )
    if "langsmith_enabled" not in observability:
        findings.append(
            ReleaseFinding(
                "langsmith_status.missing",
                "LangSmith 开关状态没有在 release summary 中显式记录。",
                {},
            )
        )
    return findings


def check_production_versions(
    production_smoke: dict[str, object],
    *,
    expected_app_version: str,
) -> list[ReleaseFinding]:
    endpoint_versions = extract_production_endpoint_versions(production_smoke)
    if not endpoint_versions:
        return [
            ReleaseFinding(
                "production_version.missing",
                "生产 smoke 没有记录 /health 或 /ready 的真实版本。",
                {"expected_app_version": expected_app_version},
            )
        ]
    mismatched_versions = {
        name: version
        for name, version in endpoint_versions.items()
        if version != expected_app_version
    }
    if not mismatched_versions:
        return []
    return [
        ReleaseFinding(
            "production_version_mismatch",
            "生产接口真实版本与本地目标版本不一致。",
            {
                "expected_app_version": expected_app_version,
                "endpoint_versions": endpoint_versions,
                "mismatched_versions": mismatched_versions,
            },
        )
    ]


def extract_production_endpoint_versions(
    production_smoke: dict[str, object],
) -> dict[str, str]:
    versions: dict[str, str] = {}
    for result in list_value(production_smoke, "checks"):
        if not isinstance(result, dict):
            continue
        name = str(result.get("name", ""))
        if name not in REQUIRED_PRODUCTION_CHECK_NAMES:
            continue
        detail = result.get("detail", "")
        if not isinstance(detail, str):
            continue
        payload = parse_detail_payload(detail)
        version = payload.get("version")
        if isinstance(version, str):
            versions[name] = version
    return versions


def parse_detail_payload(detail: str) -> dict[str, object]:
    try:
        payload = ast.literal_eval(detail)
    except (SyntaxError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_expected_version() -> str:
    return VERSION_PATH.read_text(encoding="utf-8").strip()


def read_json_report(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check LangChain production observability release evidence"
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_RELEASE_REPORT_PATH,
        help="LangChain 生产观测 release gate JSON 报告路径",
    )
    parser.add_argument(
        "--expected-version",
        help="期望生产接口返回的 APP_VERSION；默认读取 VERSION 文件",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument("--json-out", type=Path, help="写入 JSON 报告路径")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_production_observability_release_report(
        args.report,
        expected_version=args.expected_version,
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
        print_summary(report)
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_summary(report: dict[str, object]) -> None:
    production = dict_value(report, "production")
    observability = dict_value(report, "observability")
    capacity = dict_value(report, "capacity")
    endpoint_versions = dict_value(production, "endpoint_versions")
    version_values = sorted(set(str(value) for value in endpoint_versions.values()))
    print(
        "langchain_production_observability_release "
        f"status={report['status']} failed={report['failed']} "
        f"expected_version={report['expected_app_version']} "
        f"production_versions={','.join(version_values) or 'missing'} "
        f"callback_failed={production.get('callback_failed', 0)} "
        f"langsmith_enabled={str(observability.get('langsmith_enabled')).lower()} "
        f"capacity_runtime={capacity.get('production_runtime_status', 'missing')}"
    )
    for finding in list_value(report, "findings"):
        if isinstance(finding, dict):
            print(f"FAIL {finding.get('code')}: {finding.get('message')}")


def print_text_report(report: dict[str, object]) -> None:
    print("langchain_production_observability_release")
    print(f"status={report['status']} failed={report['failed']}")
    print(f"expected_app_version={report['expected_app_version']}")
    for finding in list_value(report, "findings"):
        if isinstance(finding, dict):
            print(f"FAIL {finding.get('code')}: {finding.get('message')}")


def dict_value(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def list_value(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
