"""企微员工助手自由问法规划验收。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from app.models.employee_agent import AgentPlan  # noqa: E402
from app.service.wecom.employee_agent_planner import EmployeeAgentPlanner  # noqa: E402
from scripts.wecom_employee_agent_probe_cases import (  # noqa: E402
    EmployeeAgentProbeCase,
    default_probe_cases,
)

UTF8_BOM = b"\xef\xbb\xbf"
OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"


@dataclass(frozen=True)
class AgentPlanCheck:
    name: str
    query: str
    passed: bool
    intent: str
    tools: tuple[str, ...]
    kind: str
    date_from: str
    date_to: str
    date_field: str
    statuses: tuple[str, ...]
    keyword: str
    missing_logistics: bool
    needs_refund: bool
    fulfillment_risk: bool
    delivery_time_start: str
    delivery_time_end: str
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "query": self.query,
            "passed": self.passed,
            "intent": self.intent,
            "tools": list(self.tools),
            "kind": self.kind,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "date_field": self.date_field,
            "statuses": list(self.statuses),
            "keyword": self.keyword,
            "missing_logistics": self.missing_logistics,
            "needs_refund": self.needs_refund,
            "fulfillment_risk": self.fulfillment_risk,
            "delivery_time_start": self.delivery_time_start,
            "delivery_time_end": self.delivery_time_end,
            "detail": self.detail,
        }


async def run_plan_checks(today: date | None = None) -> list[AgentPlanCheck]:
    check_date = today or date.today()
    planner = EmployeeAgentPlanner(
        today_provider=lambda: check_date,
        enable_llm=False,
    )
    checks: list[AgentPlanCheck] = []
    for probe in default_probe_cases(check_date):
        plan = await planner.plan(probe.query)
        checks.append(evaluate_probe(probe, plan))
    return checks


def evaluate_probe(probe: EmployeeAgentProbeCase, plan: AgentPlan) -> AgentPlanCheck:
    query_plan = plan.query_plan
    kind = query_plan.kind.value if query_plan else ""
    date_from = query_plan.date_from if query_plan else ""
    date_to = query_plan.date_to if query_plan else ""
    date_field = query_plan.date_field if query_plan else ""
    statuses = query_plan.statuses if query_plan else ()
    keyword = query_plan.keyword if query_plan else ""
    missing_logistics = query_plan.needs_missing_logistics if query_plan else False
    needs_refund = query_plan.needs_refund if query_plan else False
    fulfillment_risk = query_plan.needs_fulfillment_risk if query_plan else False
    delivery_time_start = query_plan.delivery_time_start if query_plan else ""
    delivery_time_end = query_plan.delivery_time_end if query_plan else ""
    mismatches = _collect_mismatches(
        probe,
        plan.intent.value,
        plan.tools,
        kind,
        date_from,
        date_to,
        date_field,
        statuses,
        keyword,
        missing_logistics,
        needs_refund,
        fulfillment_risk,
        delivery_time_start,
        delivery_time_end,
    )
    return AgentPlanCheck(
        name=probe.name,
        query=probe.query,
        passed=not mismatches,
        intent=plan.intent.value,
        tools=plan.tools,
        kind=kind,
        date_from=date_from,
        date_to=date_to,
        date_field=date_field,
        statuses=statuses,
        keyword=keyword,
        missing_logistics=missing_logistics,
        needs_refund=needs_refund,
        fulfillment_risk=fulfillment_risk,
        delivery_time_start=delivery_time_start,
        delivery_time_end=delivery_time_end,
        detail="; ".join(mismatches),
    )


def _collect_mismatches(
    probe: EmployeeAgentProbeCase,
    intent: str,
    tools: tuple[str, ...],
    kind: str,
    date_from: str,
    date_to: str,
    date_field: str,
    statuses: tuple[str, ...],
    keyword: str,
    missing_logistics: bool,
    needs_refund: bool,
    fulfillment_risk: bool,
    delivery_time_start: str,
    delivery_time_end: str,
) -> list[str]:
    mismatches: list[str] = []
    _append_mismatch(mismatches, "intent", probe.expected_intent, intent)
    _append_mismatch(mismatches, "tools", probe.expected_tools, tools)
    if probe.expected_kind:
        _append_mismatch(mismatches, "kind", probe.expected_kind, kind)
    if probe.expected_date_from:
        _append_mismatch(mismatches, "date_from", probe.expected_date_from, date_from)
    if probe.expected_date_to:
        _append_mismatch(mismatches, "date_to", probe.expected_date_to, date_to)
    if probe.expected_date_field:
        _append_mismatch(
            mismatches,
            "date_field",
            probe.expected_date_field,
            date_field,
        )
    if probe.expected_statuses:
        _append_mismatch(mismatches, "statuses", probe.expected_statuses, statuses)
    if probe.expected_keyword is not None:
        _append_mismatch(mismatches, "keyword", probe.expected_keyword, keyword)
    if probe.expected_missing_logistics is not None:
        _append_mismatch(
            mismatches,
            "missing_logistics",
            probe.expected_missing_logistics,
            missing_logistics,
        )
    if probe.expected_needs_refund is not None:
        _append_mismatch(
            mismatches,
            "needs_refund",
            probe.expected_needs_refund,
            needs_refund,
        )
    if probe.expected_fulfillment_risk is not None:
        _append_mismatch(
            mismatches,
            "fulfillment_risk",
            probe.expected_fulfillment_risk,
            fulfillment_risk,
        )
    if probe.expected_delivery_time_start:
        _append_mismatch(
            mismatches,
            "delivery_time_start",
            probe.expected_delivery_time_start,
            delivery_time_start,
        )
    if probe.expected_delivery_time_end:
        _append_mismatch(
            mismatches,
            "delivery_time_end",
            probe.expected_delivery_time_end,
            delivery_time_end,
        )
    return mismatches


def _append_mismatch(
    mismatches: list[str],
    field_name: str,
    expected_value: object,
    actual_value: object,
) -> None:
    if actual_value != expected_value:
        mismatches.append(
            f"{field_name}: expected={expected_value!r} actual={actual_value!r}"
        )


def build_report_metadata() -> dict[str, str]:
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "generated_at": generated_at,
        "project_root": str(ROOT_DIR),
        "app_version": APP_VERSION,
        "llm": "disabled",
    }


def build_json_report(checks: list[AgentPlanCheck]) -> dict[str, object]:
    failed_checks = [check for check in checks if not check.passed]
    return {
        "status": "passed" if not failed_checks else "failed",
        "metadata": build_report_metadata(),
        "total": len(checks),
        "failed": len(failed_checks),
        "checks": [check.to_dict() for check in checks],
        "failed_names": [check.name for check in failed_checks],
    }


def print_report(checks: list[AgentPlanCheck]) -> None:
    payload = build_json_report(checks)
    print("WeCom employee agent plan checks")
    print(f"generated_at={payload['metadata']['generated_at']}")
    print(f"app_version={APP_VERSION}")
    print(f"total={payload['total']} failed={payload['failed']}")
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        detail = "" if check.passed else " " + check.detail
        print(f"{status} {check.name}: {check.intent} {list(check.tools)}{detail}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check WeCom employee agent free-form planning"
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON。")
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "配合 --json 使用，将报告写入指定文件；目标文件已存在时拒绝覆盖；"
            "支持 {timestamp} 自动展开为 YYYYMMDD-HHMMSS。"
        ),
    )
    return parser.parse_args(argv)


def expand_output_path(output_path_value: str) -> Path:
    timestamp = datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)
    expanded_value = output_path_value.replace(OUTPUT_TIMESTAMP_PLACEHOLDER, timestamp)
    return Path(expanded_value)


def write_json_report(output_path: Path, json_bytes: bytes) -> None:
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(UTF8_BOM + json_bytes)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.output and not args.json:
        print("--output 必须配合 --json 使用。", file=sys.stderr)
        return 2
    output_path = expand_output_path(args.output) if args.output else None
    if output_path is not None and output_path.exists():
        print(f"报告文件已存在，拒绝覆盖: {output_path}", file=sys.stderr)
        return 2
    checks = await run_plan_checks()
    if args.json:
        json_bytes = (
            json.dumps(build_json_report(checks), ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        if output_path is not None:
            try:
                write_json_report(output_path, json_bytes)
            except FileExistsError as exc:
                print(str(exc), file=sys.stderr)
                return 2
        else:
            sys.stdout.buffer.write(json_bytes)
    else:
        print_report(checks)
    return 1 if any(not check.passed for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
