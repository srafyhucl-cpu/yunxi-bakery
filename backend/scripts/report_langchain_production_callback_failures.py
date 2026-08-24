"""生成 LangChain 生产 callback 失败定位报告。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts.wecom_employee_agent_probe_cases import (  # noqa: E402
    EmployeeAgentProbeCase,
    default_probe_cases,
)

DEFAULT_CALLBACK_REPORT_PATTERN = (
    ROOT_DIR / "reports" / "wecom-employee-agent" / "langchain-prod-callback-*.json"
)
DEFAULT_HANDOFF_REPORT_PATH = (
    ROOT_DIR / "reports" / "harness" / "langchain-production-sync-handoff-latest.json"
)
DEFAULT_OUTPUT_PATH = (
    ROOT_DIR
    / "reports"
    / "harness"
    / "langchain-production-callback-failures-latest.json"
)


@dataclass(frozen=True)
class CallbackFailure:
    name: str
    query: str
    detail: str
    content_preview: str
    reply_valid: bool
    privacy_safe: bool
    semantic_safe: bool
    diagnosis_code: str
    recommendation: str
    expected: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "query": self.query,
            "detail": self.detail,
            "content_preview": self.content_preview,
            "reply_valid": self.reply_valid,
            "privacy_safe": self.privacy_safe,
            "semantic_safe": self.semantic_safe,
            "diagnosis_code": self.diagnosis_code,
            "recommendation": self.recommendation,
            "expected": self.expected,
        }


def build_callback_failure_report(
    *,
    callback_report_path: Path | None = None,
    handoff_report_path: Path = DEFAULT_HANDOFF_REPORT_PATH,
    today: date | None = None,
) -> dict[str, object]:
    resolved_callback_path = callback_report_path or resolve_latest_callback_report()
    callback_report = read_json_report(resolved_callback_path)
    handoff_report = read_json_report(handoff_report_path)
    runtime = dict_value(handoff_report, "runtime_check")
    probe_case_map = build_probe_case_map(today or date.today())
    failed_results = [
        result
        for result in list_value(callback_report, "results")
        if isinstance(result, dict) and result.get("passed") is not True
    ]
    runtime_status = str(runtime.get("status", "missing"))
    failures = [
        build_callback_failure(
            result,
            probe_case_map.get(str(result.get("name", ""))),
            runtime_status=runtime_status,
        )
        for result in failed_results
    ]
    status = determine_report_status(runtime_status, failures)
    return {
        "status": status,
        "generated_at": utc_now(),
        "trace_id": "20260709-langchain-ai-layer-production-enhancement",
        "phase": "P14-production-callback-failure-diagnosis",
        "callback_report": str(resolved_callback_path),
        "handoff_report": str(handoff_report_path),
        "runtime": {
            "status": runtime_status,
            "expected_version": runtime.get("expected_version", ""),
            "endpoint_versions": runtime.get("endpoint_versions", {}),
            "failed_names": runtime.get("failed_names", []),
        },
        "callback": {
            "status": callback_report.get("status", "missing"),
            "total": callback_report.get("total", 0),
            "failed": len(failures),
            "failed_names": [failure.name for failure in failures],
            "base_url": dict_value(callback_report, "metadata").get("base_url", ""),
            "app_version": dict_value(callback_report, "metadata").get(
                "app_version", ""
            ),
        },
        "failures": [failure.to_dict() for failure in failures],
        "next_actions": build_next_actions(runtime_status, failures),
    }


def resolve_latest_callback_report() -> Path:
    candidates = sorted(
        DEFAULT_CALLBACK_REPORT_PATTERN.parent.glob(
            DEFAULT_CALLBACK_REPORT_PATTERN.name
        )
    )
    if not candidates:
        raise FileNotFoundError(
            "未找到生产 callback 报告: " + str(DEFAULT_CALLBACK_REPORT_PATTERN)
        )
    return max(candidates, key=lambda path: path.name)


def read_json_report(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_probe_case_map(today: date) -> dict[str, EmployeeAgentProbeCase]:
    return {case.name: case for case in default_probe_cases(today)}


def build_callback_failure(
    result: dict[str, object],
    probe_case: EmployeeAgentProbeCase | None,
    *,
    runtime_status: str,
) -> CallbackFailure:
    diagnosis_code = classify_failure(result, probe_case, runtime_status)
    return CallbackFailure(
        name=str(result.get("name", "")),
        query=str(result.get("query", "")),
        detail=str(result.get("detail", "")),
        content_preview=str(result.get("content_preview", "")),
        reply_valid=bool(result.get("reply_valid", False)),
        privacy_safe=bool(result.get("privacy_safe", False)),
        semantic_safe=bool(result.get("semantic_safe", False)),
        diagnosis_code=diagnosis_code,
        recommendation=recommend_failure_action(diagnosis_code, runtime_status),
        expected=build_expected_payload(probe_case),
    )


def classify_failure(
    result: dict[str, object],
    probe_case: EmployeeAgentProbeCase | None,
    runtime_status: str,
) -> str:
    if runtime_status != "passed":
        return "runtime_version_not_current"
    if result.get("reply_valid") is not True:
        return "callback_reply_invalid"
    if result.get("privacy_safe") is not True:
        return "privacy_violation"
    content_preview = str(result.get("content_preview", ""))
    if probe_case and probe_case.expected_intent == "knowledge_answer":
        if "未找到匹配知识" in content_preview:
            return "production_knowledge_missing_or_old_retrieval"
    if probe_case and probe_case.expected_intent == "order_query":
        if "没有查到" in content_preview:
            return "data_dependent_empty_result"
    if result.get("semantic_safe") is not True:
        return "semantic_mismatch"
    return "unknown_failure"


def recommend_failure_action(diagnosis_code: str, runtime_status: str) -> str:
    if runtime_status != "passed":
        return "先同步并重启生产到目标 VERSION，待 runtime gate 通过后再复跑 callback。"
    recommendations = {
        "callback_reply_invalid": "检查 callback 加密回复格式、msgtype=stream 和 finish 字段。",
        "privacy_violation": "先修复隐私输出，再复跑 callback，不得放宽隐私断言。",
        "production_knowledge_missing_or_old_retrieval": "检查生产员工知识库是否已发布退款规则，并复核知识检索链路。",
        "data_dependent_empty_result": "核对生产当日订单数据；若允许空结果，需要为该 case 增加受控空状态语义。",
        "semantic_mismatch": "比较期望语义与实际回复，确认是业务缺口还是断言过窄。",
    }
    return recommendations.get(diagnosis_code, "保留失败证据并人工复核。")


def build_expected_payload(
    probe_case: EmployeeAgentProbeCase | None,
) -> dict[str, object]:
    if probe_case is None:
        return {}
    return {
        "expected_intent": probe_case.expected_intent,
        "expected_tools": list(probe_case.expected_tools),
        "expected_kind": probe_case.expected_kind,
        "expected_statuses": list(probe_case.expected_statuses),
        "expected_keyword": probe_case.expected_keyword or "",
        "required_any_terms": list(probe_case.required_any_terms),
        "required_all_terms": list(probe_case.required_all_terms),
        "required_all_term_groups": [
            list(group) for group in probe_case.required_all_term_groups
        ],
        "forbidden_terms": list(probe_case.forbidden_terms),
    }


def determine_report_status(
    runtime_status: str,
    failures: list[CallbackFailure],
) -> str:
    if runtime_status != "passed" and failures:
        return "blocked"
    if failures:
        return "failed"
    return "passed"


def build_next_actions(
    runtime_status: str,
    failures: list[CallbackFailure],
) -> list[str]:
    if runtime_status != "passed":
        return [
            "先完成 P14c：同步生产 worktree、重启 yunxibakebot，并让 runtime gate 通过。",
            "runtime gate 通过后复跑 production release gate 和 callback probe。",
            "只有新版本 callback 仍失败时，才进入具体业务或断言修复。",
        ]
    if not failures:
        return ["callback probe 已通过，可继续 P14 发布证据收口。"]
    return [
        "按 failures[].diagnosis_code 逐项定位，不得放宽版本门禁或隐私断言。",
        "修复后复跑 callback probe、P13b 发布证据门禁和 P14 handoff。",
    ]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build production callback failure diagnosis report"
    )
    parser.add_argument("--callback-report", type=Path, help="生产 callback JSON 报告")
    parser.add_argument(
        "--handoff-report",
        type=Path,
        default=DEFAULT_HANDOFF_REPORT_PATH,
        help="P14 handoff JSON 报告",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument("--json-out", type=Path, help="写入 JSON 报告路径")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = build_callback_failure_report(
            callback_report_path=args.callback_report,
            handoff_report_path=args.handoff_report,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
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
    callback = dict_value(report, "callback")
    runtime = dict_value(report, "runtime")
    print(
        "langchain_production_callback_failures "
        f"status={report['status']} failed={callback.get('failed', 0)} "
        f"runtime_status={runtime.get('status', 'missing')} "
        f"app_version={callback.get('app_version', '')}"
    )
    for failure in list_value(report, "failures"):
        if isinstance(failure, dict):
            print(
                f"FAIL {failure.get('name')}: "
                f"{failure.get('diagnosis_code')} {failure.get('detail')}"
            )


def print_text_report(report: dict[str, object]) -> None:
    print("langchain_production_callback_failures")
    print(f"status={report['status']}")
    for action in list_value(report, "next_actions"):
        print(f"- {action}")


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
