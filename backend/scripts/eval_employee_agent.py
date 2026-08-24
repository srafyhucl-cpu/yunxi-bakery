"""员工助手离线 eval 报告。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from app.service.agents.evaluation import (  # noqa: E402
    AgentEvalAssertion,
    AgentEvalCase,
    AgentEvalResult,
    apply_fail_fast,
    filter_agent_eval_result,
    write_json_report,
)
from scripts import check_employee_agent_capability_contracts  # noqa: E402
from scripts.check_wecom_employee_agent_plans import run_plan_checks  # noqa: E402


async def build_employee_eval_result() -> AgentEvalResult:
    plan_checks = await run_plan_checks()
    capability_checks = check_employee_agent_capability_contracts.run_checks()
    plan_cases = tuple(
        AgentEvalCase(
            case_id=check.name,
            agent="employee",
            query=check.query,
            group="planner",
            intent=check.intent,
            tools=check.tools,
            assertions=(
                AgentEvalAssertion(
                    "planner.expected_shape", check.passed, check.detail
                ),
            ),
            metadata={
                "kind": check.kind,
                "date_field": check.date_field,
                "statuses": list(check.statuses),
            },
        )
        for check in plan_checks
    )
    capability_case = AgentEvalCase(
        case_id="employee.capability_contracts",
        agent="employee",
        query="",
        group="capability_contracts",
        intent="governance",
        assertions=tuple(
            AgentEvalAssertion(check.name, check.passed, check.detail)
            for check in capability_checks
        ),
    )
    return AgentEvalResult(
        agent="employee",
        cases=(capability_case, *plan_cases),
        metadata=_metadata(),
    )


def _metadata() -> dict[str, object]:
    return {
        "generated_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "project_root": str(ROOT_DIR),
        "app_version": APP_VERSION,
        "llm": "disabled",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Eval employee agent offline cases")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument("--json-out", type=Path, help="写入 JSON 报告路径")
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="只运行指定 case_id，可重复传入",
    )
    parser.add_argument("--fail-fast", action="store_true", help="首个失败后停止报告")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    result = await build_employee_eval_result()
    result = filter_agent_eval_result(result, tuple(args.case_id))
    if args.fail_fast:
        result = apply_fail_fast(result)
    payload = result.to_dict()
    if args.json_out is not None:
        write_json_report(payload, args.json_out)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "employee_agent_eval "
            f"status={result.status} total={result.total} failed={result.failed} "
            f"pass_rate={result.pass_rate}"
        )
    else:
        print_text_report(result)
    return 0 if result.status == "passed" else 1


def print_text_report(result: AgentEvalResult) -> None:
    print("employee_agent_eval")
    print(
        f"status={result.status} total={result.total} "
        f"failed={result.failed} pass_rate={result.pass_rate}"
    )
    for case in result.cases:
        mark = "PASS" if case.passed else "FAIL"
        print(f"{mark} {case.case_id} {case.intent} {list(case.tools)}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
