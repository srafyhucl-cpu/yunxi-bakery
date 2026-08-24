"""脱敏真实会话回复回放检查。"""

from __future__ import annotations

import argparse
import json
import re
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
    FIXTURE_PATH as CUSTOMER_GOLDEN_FIXTURE_PATH,
    build_forbidden_reply_patterns,
    load_fixture,
)

DEFAULT_REAL_REPLAY_FIXTURE_PATH = (
    ROOT_DIR / "tests" / "fixtures" / "customer_real_replay_sample.json"
)
PRIVACY_PATTERNS = (
    re.compile(r"1[3-9]\d{9}"),
    re.compile(r"\b[A-Z]?\d{14,}\b"),
    re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        re.IGNORECASE,
    ),
    re.compile(r"(open_id|unionid|手机号|电话|完整地址|收货地址|完整订单号)"),
)


def build_real_conversation_replay_result(
    replay_fixture_path: Path = DEFAULT_REAL_REPLAY_FIXTURE_PATH,
    customer_fixture_path: Path = CUSTOMER_GOLDEN_FIXTURE_PATH,
) -> AgentEvalResult:
    replay_payload = _load_json_object(replay_fixture_path)
    golden_case_map = build_sensitive_golden_case_map(customer_fixture_path)
    contains_sensitive_data_declared_false = (
        _metadata_raw_value(replay_payload, "contains_sensitive_data") is False
    )
    cases = tuple(
        build_real_replay_case(
            case_payload,
            golden_case_map,
            contains_sensitive_data_declared_false=contains_sensitive_data_declared_false,
        )
        for case_payload in _extract_cases(replay_payload)
    )
    return AgentEvalResult(
        agent="real_conversation_replay",
        cases=cases,
        metadata={
            "generated_at": _generated_at(),
            "project_root": str(ROOT_DIR),
            "app_version": APP_VERSION,
            "fixture": str(replay_fixture_path),
            "customer_fixture": str(customer_fixture_path),
            "source": _metadata_value(replay_payload, "source"),
            "redaction": _metadata_value(replay_payload, "redaction"),
            "contains_sensitive_data": _metadata_bool(
                replay_payload, "contains_sensitive_data"
            ),
            "llm": "disabled",
        },
    )


def build_sensitive_golden_case_map(
    customer_fixture_path: Path,
) -> dict[str, dict[str, Any]]:
    payload = load_fixture(customer_fixture_path)
    case_map: dict[str, dict[str, Any]] = {}
    for case in payload.get("cases", []):
        if not isinstance(case, dict) or not case.get("sensitive_scenarios"):
            continue
        case_id = str(case.get("id", "")).strip()
        if case_id:
            case_map[case_id] = case
    return case_map


def build_real_replay_case(
    case_payload: dict[str, Any],
    golden_case_map: dict[str, dict[str, Any]],
    *,
    contains_sensitive_data_declared_false: bool,
) -> AgentEvalCase:
    case_id = str(case_payload.get("case_id", "")).strip()
    golden_case_id = str(case_payload.get("golden_case_id", "")).strip()
    user_message = str(case_payload.get("user_message", "")).strip()
    final_reply = str(case_payload.get("final_reply", "")).strip()
    golden_case = golden_case_map.get(golden_case_id, {})
    forbidden_patterns = (
        build_forbidden_reply_patterns(golden_case) if golden_case else []
    )
    matched_patterns = [
        pattern for pattern in forbidden_patterns if pattern and pattern in final_reply
    ]
    privacy_hits = find_privacy_hits(user_message + "\n" + final_reply)
    return AgentEvalCase(
        case_id=case_id,
        agent="real_conversation_replay",
        query=user_message,
        group=str(case_payload.get("group") or golden_case.get("group") or ""),
        intent=str(case_payload.get("intent") or golden_case.get("intent") or ""),
        assertions=(
            AgentEvalAssertion(
                "fixture.contains_sensitive_data_false",
                contains_sensitive_data_declared_false,
            ),
            AgentEvalAssertion("case_id.present", bool(case_id)),
            AgentEvalAssertion("golden_case_id.sensitive", bool(golden_case)),
            AgentEvalAssertion("user_message.present", bool(user_message)),
            AgentEvalAssertion("final_reply.present", bool(final_reply)),
            AgentEvalAssertion(
                "privacy_patterns.absent",
                not privacy_hits,
                "" if not privacy_hits else "matched privacy patterns",
            ),
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
            "golden_case_id": golden_case_id,
            "source": str(case_payload.get("source", "")),
            "sensitive_scenarios": golden_case.get("sensitive_scenarios", []),
            "forbidden_reply_patterns": forbidden_patterns,
            "matched_forbidden_patterns": matched_patterns,
            "privacy_hits": privacy_hits,
        },
    )


def find_privacy_hits(text: str) -> list[str]:
    hits = []
    for pattern in PRIVACY_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


def build_reply_replay_payload(
    result: AgentEvalResult,
    replay_fixture_path: Path,
) -> dict[str, object]:
    final_reply_by_case_id = {
        str(case.get("case_id", "")).strip(): str(case.get("final_reply", "")).strip()
        for case in _extract_cases(_load_json_object(replay_fixture_path))
    }
    replies = []
    seen_golden_case_ids: set[str] = set()
    for case in result.cases:
        golden_case_id = str(case.metadata.get("golden_case_id", "")).strip()
        if not golden_case_id or golden_case_id in seen_golden_case_ids:
            continue
        seen_golden_case_ids.add(golden_case_id)
        replies.append(
            {
                "case_id": golden_case_id,
                "reply": final_reply_by_case_id.get(case.case_id, ""),
                "source_case_id": case.case_id,
            }
        )
    return {
        "metadata": {
            "source": "real_conversation_replay",
            "generated_at": _generated_at(),
            "app_version": APP_VERSION,
            "contains_sensitive_data": False,
        },
        "replies": replies,
    }


def ensure_unique_golden_case_ids(result: AgentEvalResult) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for case in result.cases:
        golden_case_id = str(case.metadata.get("golden_case_id", "")).strip()
        if not golden_case_id:
            continue
        if golden_case_id in seen:
            duplicates.append(golden_case_id)
        seen.add(golden_case_id)
    if duplicates:
        raise ValueError("重复 golden_case_id: " + ", ".join(sorted(set(duplicates))))


def _load_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {}


def _extract_cases(payload: dict[str, object]) -> list[dict[str, Any]]:
    cases = payload.get("cases")
    if not isinstance(cases, list):
        return []
    return [case for case in cases if isinstance(case, dict)]


def _metadata_value(payload: dict[str, object], key: str) -> str:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    value = metadata.get(key)
    return str(value) if value is not None else ""


def _metadata_bool(payload: dict[str, object], key: str) -> bool:
    return _metadata_raw_value(payload, key) is True


def _metadata_raw_value(payload: dict[str, object], key: str) -> object:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return None
    return metadata.get(key)


def _generated_at() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check sanitized real customer conversation replay cases"
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
        "--case-id",
        action="append",
        default=[],
        help="只运行指定 replay case_id，可重复传入",
    )
    parser.add_argument("--fail-fast", action="store_true", help="首个失败后停止报告")
    parser.add_argument(
        "--replies-json-out",
        type=Path,
        help="导出兼容 check_customer_reply_replay.py --replies-json 的回复映射",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    result = build_real_conversation_replay_result(
        replay_fixture_path=args.fixture,
        customer_fixture_path=args.customer_fixture,
    )
    result = filter_agent_eval_result(result, tuple(args.case_id))
    if args.fail_fast:
        result = apply_fail_fast(result)
    payload = result.to_dict()
    if args.json_out is not None:
        write_json_report(payload, args.json_out)
    if args.replies_json_out is not None:
        ensure_unique_golden_case_ids(result)
        write_json_report(
            build_reply_replay_payload(result, args.fixture),
            args.replies_json_out,
        )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "real_conversation_replay "
            f"status={result.status} total={result.total} failed={result.failed} "
            f"pass_rate={result.pass_rate}"
        )
    else:
        print_text_report(result)
    return 0 if result.status == "passed" else 1


def print_text_report(result: AgentEvalResult) -> None:
    print("real_conversation_replay")
    print(
        f"status={result.status} total={result.total} "
        f"failed={result.failed} pass_rate={result.pass_rate}"
    )
    for case in result.cases:
        mark = "PASS" if case.passed else "FAIL"
        print(f"{mark} {case.case_id} {case.group}".rstrip())


if __name__ == "__main__":
    raise SystemExit(main())
