"""客户机器人回复回放安全检查。"""

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
    build_forbidden_reply_patterns,
    load_fixture,
)

DEFAULT_SAFE_REPLY = (
    "这类问题需要按订单、库存或门店实时情况确认，我会先收集必要信息并协助转人工处理。"
)


def build_customer_reply_replay_result(
    fixture_path: Path = FIXTURE_PATH,
    reply_json_path: Path | None = None,
) -> AgentEvalResult:
    payload = load_fixture(fixture_path)
    reply_map = load_reply_map(reply_json_path) if reply_json_path else {}
    case_payloads = [
        case
        for case in payload.get("cases", [])
        if isinstance(case, dict) and case.get("sensitive_scenarios")
    ]
    cases = tuple(_build_reply_replay_case(case, reply_map) for case in case_payloads)
    return AgentEvalResult(
        agent="customer_reply_replay",
        cases=cases,
        metadata={
            "generated_at": _generated_at(),
            "project_root": str(ROOT_DIR),
            "app_version": APP_VERSION,
            "fixture": str(fixture_path),
            "reply_source": str(reply_json_path) if reply_json_path else "default_safe",
            "llm": "disabled",
        },
    )


def load_reply_map(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and all(
        isinstance(case_id, str) and isinstance(reply, str)
        for case_id, reply in payload.items()
    ):
        return dict(payload)
    records = _extract_reply_records(payload)
    reply_map: dict[str, str] = {}
    for record in records:
        case_id = str(record.get("case_id") or record.get("id") or "").strip()
        reply = str(record.get("reply") or record.get("text") or "").strip()
        if case_id and reply:
            reply_map[case_id] = reply
    return reply_map


def _extract_reply_records(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("replies", "cases", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _build_reply_replay_case(
    case: dict[str, Any],
    reply_map: dict[str, str],
) -> AgentEvalCase:
    case_id = str(case.get("id", ""))
    reply = reply_map.get(case_id, DEFAULT_SAFE_REPLY)
    forbidden_patterns = build_forbidden_reply_patterns(case)
    matched_patterns = [
        pattern for pattern in forbidden_patterns if pattern and pattern in reply
    ]
    return AgentEvalCase(
        case_id=case_id,
        agent="customer_reply_replay",
        query=str(case.get("query", "")),
        group=str(case.get("group", "")),
        intent=str(case.get("intent", "")),
        assertions=(
            AgentEvalAssertion("reply.present", bool(reply.strip())),
            AgentEvalAssertion(
                "forbidden_reply_patterns.absent",
                not matched_patterns,
                (
                    ""
                    if not matched_patterns
                    else "matched forbidden patterns: " + ", ".join(matched_patterns)
                ),
            ),
        ),
        metadata={
            "sensitive_scenarios": case.get("sensitive_scenarios", []),
            "forbidden_reply_patterns": forbidden_patterns,
            "matched_forbidden_patterns": matched_patterns,
            "reply_source": "input" if case_id in reply_map else "default_safe",
        },
    )


def _generated_at() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check customer reply replay safety")
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
        "--fixture",
        default=str(FIXTURE_PATH),
        help="客户 eval fixture",
    )
    parser.add_argument(
        "--replies-json",
        type=Path,
        help="回复回放 JSON，支持 case_id 到 reply 的映射或 replies/cases/results 列表",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    result = build_customer_reply_replay_result(
        fixture_path=Path(args.fixture),
        reply_json_path=args.replies_json,
    )
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
            "customer_reply_replay "
            f"status={result.status} total={result.total} failed={result.failed} "
            f"pass_rate={result.pass_rate}"
        )
    else:
        print_text_report(result)
    return 0 if result.status == "passed" else 1


def print_text_report(result: AgentEvalResult) -> None:
    print("customer_reply_replay")
    print(
        f"status={result.status} total={result.total} "
        f"failed={result.failed} pass_rate={result.pass_rate}"
    )
    for case in result.cases:
        mark = "PASS" if case.passed else "FAIL"
        print(f"{mark} {case.case_id} {case.group}".rstrip())


if __name__ == "__main__":
    raise SystemExit(main())
