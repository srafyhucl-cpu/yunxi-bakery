"""脱敏真实会话 replay 场景覆盖率检查。"""

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
from scripts.check_customer_rag_golden_cases import (  # noqa: E402
    FIXTURE_PATH as CUSTOMER_GOLDEN_FIXTURE_PATH,
    load_fixture,
)
from scripts.check_real_conversation_replay import (  # noqa: E402
    DEFAULT_REAL_REPLAY_FIXTURE_PATH,
    build_real_conversation_replay_result,
)

DEFAULT_MIN_PER_SCENARIO = 5


def build_real_replay_coverage_report(
    *,
    replay_fixture_path: Path = DEFAULT_REAL_REPLAY_FIXTURE_PATH,
    customer_fixture_path: Path = CUSTOMER_GOLDEN_FIXTURE_PATH,
    required_scenarios: tuple[str, ...] = (),
    min_per_scenario: int = DEFAULT_MIN_PER_SCENARIO,
) -> dict[str, object]:
    replay_result = build_real_conversation_replay_result(
        replay_fixture_path=replay_fixture_path,
        customer_fixture_path=customer_fixture_path,
    )
    required = required_scenarios or load_required_sensitive_scenarios(
        customer_fixture_path
    )
    counts = {scenario: 0 for scenario in required}
    case_ids = {scenario: [] for scenario in required}
    for case in replay_result.cases:
        scenarios = case.metadata.get("sensitive_scenarios", [])
        if not isinstance(scenarios, list):
            continue
        for scenario in scenarios:
            scenario_name = str(scenario)
            if scenario_name not in counts:
                continue
            counts[scenario_name] += 1
            case_ids[scenario_name].append(case.case_id)
    scenario_coverage = [
        {
            "scenario": scenario,
            "total": counts[scenario],
            "required": min_per_scenario,
            "passed": counts[scenario] >= min_per_scenario,
            "case_ids": case_ids[scenario],
        }
        for scenario in required
    ]
    failed = sum(1 for item in scenario_coverage if not item["passed"])
    if replay_result.status != "passed":
        failed += 1
    return {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": generated_at(),
        "app_version": APP_VERSION,
        "fixture": str(replay_fixture_path),
        "customer_fixture": str(customer_fixture_path),
        "replay_status": replay_result.status,
        "replay_total": replay_result.total,
        "replay_failed": replay_result.failed,
        "min_per_scenario": min_per_scenario,
        "total": len(required),
        "failed": failed,
        "scenario_coverage": scenario_coverage,
    }


def load_required_sensitive_scenarios(customer_fixture_path: Path) -> tuple[str, ...]:
    payload = load_fixture(customer_fixture_path)
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return ()
    scenarios = meta.get("required_sensitive_scenarios")
    if not isinstance(scenarios, list):
        return ()
    return tuple(str(scenario) for scenario in scenarios if str(scenario).strip())


def generated_at() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check sanitized real conversation replay scenario coverage"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument("--json-out", type=Path, help="写入 JSON 报告路径")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_REAL_REPLAY_FIXTURE_PATH,
        help="脱敏真实会话 replay fixture",
    )
    parser.add_argument(
        "--customer-fixture",
        type=Path,
        default=CUSTOMER_GOLDEN_FIXTURE_PATH,
        help="客户 golden cases fixture",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="要求覆盖的敏感场景；默认读取客户 golden fixture 的 required_sensitive_scenarios",
    )
    parser.add_argument(
        "--min-per-scenario",
        type=int,
        default=DEFAULT_MIN_PER_SCENARIO,
        help="每个敏感场景至少需要的 replay case 数",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_real_replay_coverage_report(
        replay_fixture_path=args.fixture,
        customer_fixture_path=args.customer_fixture,
        required_scenarios=tuple(args.scenario),
        min_per_scenario=args.min_per_scenario,
    )
    if args.json_out is not None:
        write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "real_conversation_replay_coverage "
            f"status={report['status']} total={report['total']} "
            f"failed={report['failed']} min_per_scenario={report['min_per_scenario']}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_text_report(report: dict[str, object]) -> None:
    print("real_conversation_replay_coverage")
    print(
        f"status={report['status']} total={report['total']} failed={report['failed']}"
    )
    for item in report["scenario_coverage"]:
        mark = "PASS" if item["passed"] else "FAIL"
        print(f"{mark} {item['scenario']} total={item['total']}")


if __name__ == "__main__":
    raise SystemExit(main())
