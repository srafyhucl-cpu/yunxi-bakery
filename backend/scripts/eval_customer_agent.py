"""客户机器人离线 eval 报告。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
from scripts.check_customer_rag_golden_cases import (  # noqa: E402
    FIXTURE_PATH,
    REQUIRED_GROUPS,
    build_forbidden_reply_patterns,
    build_sensitive_policy_checks,
    load_fixture,
    validate_fixture,
)


def build_customer_eval_result(fixture_path: Path = FIXTURE_PATH) -> AgentEvalResult:
    payload = load_fixture(fixture_path)
    fixture_checks = validate_fixture(payload)
    case_payloads = [
        case for case in payload.get("cases", []) if isinstance(case, dict)
    ]
    cases = tuple(_build_eval_case(case) for case in case_payloads)
    fixture_case = AgentEvalCase(
        case_id="customer.fixture_governance",
        agent="customer",
        query="",
        group="fixture_governance",
        intent="governance",
        assertions=tuple(
            AgentEvalAssertion(check.name, check.passed, check.detail)
            for check in fixture_checks
        ),
        metadata={"fixture": str(fixture_path)},
    )
    return AgentEvalResult(
        agent="customer",
        cases=(fixture_case, *cases),
        metadata=_metadata(fixture_path),
    )


def _build_eval_case(case: dict[str, Any]) -> AgentEvalCase:
    relevant = case.get("relevant")
    guardrails = case.get("guardrails")
    sensitive_scenarios = case.get("sensitive_scenarios")
    forbidden_reply_patterns = build_forbidden_reply_patterns(case)
    group = str(case.get("group", ""))
    return AgentEvalCase(
        case_id=str(case.get("id", "")),
        agent="customer",
        query=str(case.get("query", "")),
        group=group,
        intent=str(case.get("intent", "")),
        assertions=(
            AgentEvalAssertion(
                "query.present",
                bool(str(case.get("query", "")).strip()),
            ),
            AgentEvalAssertion(
                "group.supported",
                group in REQUIRED_GROUPS,
                "" if group in REQUIRED_GROUPS else f"group={group}",
            ),
            AgentEvalAssertion(
                "relevant.matchers",
                _has_nested_text(relevant),
            ),
            AgentEvalAssertion(
                "guardrails.present",
                _has_text_list(guardrails),
            ),
            AgentEvalAssertion(
                "forbidden_reply_patterns.present",
                not isinstance(sensitive_scenarios, list)
                or bool(forbidden_reply_patterns),
            ),
            *(
                AgentEvalAssertion(
                    _sensitive_policy_assertion_name(check.name),
                    check.passed,
                    check.detail,
                )
                for check in build_sensitive_policy_checks(case)
            ),
        ),
        metadata={
            "relevant_count": len(relevant) if isinstance(relevant, list) else 0,
            "guardrail_count": len(guardrails) if isinstance(guardrails, list) else 0,
            "sensitive_scenarios": sensitive_scenarios
            if isinstance(sensitive_scenarios, list)
            else [],
            "forbidden_reply_patterns": forbidden_reply_patterns,
        },
    )


def _sensitive_policy_assertion_name(check_name: str) -> str:
    parts = check_name.rsplit(".", maxsplit=2)
    if len(parts) < 3:
        return check_name
    return f"{parts[-2]}.{parts[-1]}"


def _has_nested_text(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_has_text_list(item) for item in value)
    )


def _has_text_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _metadata(fixture_path: Path) -> dict[str, object]:
    return {
        "generated_at": _generated_at(),
        "project_root": str(ROOT_DIR),
        "app_version": APP_VERSION,
        "fixture": str(fixture_path),
        "llm": "disabled",
    }


def _generated_at() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace(
            "+00:00",
            "Z",
        )
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Eval customer agent offline cases")
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
    parser.add_argument(
        "--fixture", default=str(FIXTURE_PATH), help="客户 eval fixture"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    result = build_customer_eval_result(Path(args.fixture))
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
            "customer_agent_eval "
            f"status={result.status} total={result.total} failed={result.failed} "
            f"pass_rate={result.pass_rate}"
        )
    else:
        print_text_report(result)
    return 0 if result.status == "passed" else 1


def print_text_report(result: AgentEvalResult) -> None:
    print("customer_agent_eval")
    print(
        f"status={result.status} total={result.total} "
        f"failed={result.failed} pass_rate={result.pass_rate}"
    )
    for case in result.cases:
        mark = "PASS" if case.passed else "FAIL"
        print(f"{mark} {case.case_id} {case.group}".rstrip())


if __name__ == "__main__":
    raise SystemExit(main())
