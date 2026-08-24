"""双机器人 Agent Eval 聚合报告。"""

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
    AgentEvalResult,
    apply_fail_fast,
    combine_agent_eval_results,
    filter_agent_eval_result,
    write_json_report,
)
from scripts.check_customer_reply_replay import (  # noqa: E402
    build_customer_reply_replay_result,
)
from scripts.check_real_conversation_replay import (  # noqa: E402
    DEFAULT_REAL_REPLAY_FIXTURE_PATH,
    build_real_conversation_replay_result,
)
from scripts.eval_customer_agent import build_customer_eval_result  # noqa: E402
from scripts.eval_employee_agent import build_employee_eval_result  # noqa: E402


async def build_agent_eval_report(
    *,
    agent: str = "all",
    case_ids: tuple[str, ...] = (),
    fail_fast: bool = False,
    include_reply_replay: bool = False,
    reply_replay_json: Path | None = None,
    include_real_replay: bool = False,
    real_replay_fixture: Path | None = None,
) -> dict[str, object]:
    results = await _build_selected_results(
        agent,
        include_reply_replay=include_reply_replay,
        reply_replay_json=reply_replay_json,
        include_real_replay=include_real_replay,
        real_replay_fixture=real_replay_fixture,
    )
    if case_ids:
        results = tuple(
            filter_agent_eval_result(result, case_ids) for result in results
        )
    if fail_fast:
        results = tuple(apply_fail_fast(result) for result in results)
    return combine_agent_eval_results(
        results,
        metadata={
            "generated_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "project_root": str(ROOT_DIR),
            "app_version": APP_VERSION,
            "llm": "disabled",
            "agent_filter": agent,
            "case_filter": list(case_ids),
            "fail_fast": fail_fast,
            "include_reply_replay": include_reply_replay,
            "reply_replay_source": str(reply_replay_json) if reply_replay_json else "",
            "include_real_replay": include_real_replay,
            "real_replay_source": str(real_replay_fixture or ""),
        },
    )


async def _build_selected_results(
    agent: str,
    *,
    include_reply_replay: bool,
    reply_replay_json: Path | None,
    include_real_replay: bool,
    real_replay_fixture: Path | None,
) -> tuple[AgentEvalResult, ...]:
    if agent == "customer":
        return (build_customer_eval_result(),)
    if agent == "employee":
        return (await build_employee_eval_result(),)
    if agent == "customer_reply_replay":
        return (build_customer_reply_replay_result(reply_json_path=reply_replay_json),)
    if agent == "real_conversation_replay":
        return (
            build_real_conversation_replay_result(
                replay_fixture_path=real_replay_fixture
                or DEFAULT_REAL_REPLAY_FIXTURE_PATH,
            ),
        )
    results: list[AgentEvalResult] = [
        build_customer_eval_result(),
        await build_employee_eval_result(),
    ]
    if include_reply_replay:
        results.append(
            build_customer_reply_replay_result(reply_json_path=reply_replay_json)
        )
    if include_real_replay:
        results.append(
            build_real_conversation_replay_result(
                replay_fixture_path=real_replay_fixture
                or DEFAULT_REAL_REPLAY_FIXTURE_PATH,
            )
        )
    return tuple(results)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report combined agent eval")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument("--json-out", type=Path, help="写入 JSON 报告路径")
    parser.add_argument(
        "--agent",
        choices=(
            "customer",
            "employee",
            "customer_reply_replay",
            "real_conversation_replay",
            "all",
        ),
        default="all",
        help="选择 eval agent",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="只报告指定 case_id，可重复传入",
    )
    parser.add_argument("--fail-fast", action="store_true", help="首个失败后停止报告")
    parser.add_argument(
        "--include-reply-replay",
        action="store_true",
        help="在 all 聚合报告中额外包含客户回复回放检查",
    )
    parser.add_argument(
        "--reply-replay-json",
        type=Path,
        help="客户回复回放 JSON，传给 customer_reply_replay eval",
    )
    parser.add_argument(
        "--include-real-replay",
        action="store_true",
        help="在 all 聚合报告中额外包含脱敏真实会话回复回放检查",
    )
    parser.add_argument(
        "--real-replay-fixture",
        type=Path,
        default=DEFAULT_REAL_REPLAY_FIXTURE_PATH,
        help="脱敏真实会话 replay fixture",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="输出当前最新 eval 文本报告；与默认行为一致，便于计划命令稳定",
    )
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    payload = await build_agent_eval_report(
        agent=args.agent,
        case_ids=tuple(args.case_id),
        fail_fast=args.fail_fast,
        include_reply_replay=args.include_reply_replay,
        reply_replay_json=args.reply_replay_json,
        include_real_replay=args.include_real_replay,
        real_replay_fixture=args.real_replay_fixture,
    )
    if args.json_out is not None:
        write_json_report(payload, args.json_out)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "agent_eval "
            f"status={payload['status']} total={payload['total']} "
            f"failed={payload['failed']} pass_rate={payload['pass_rate']}"
        )
    else:
        print_text_report(payload)
    return 0 if payload["status"] == "passed" else 1


def print_text_report(payload: dict[str, object]) -> None:
    print("agent_eval")
    print(
        f"status={payload['status']} total={payload['total']} "
        f"failed={payload['failed']} pass_rate={payload['pass_rate']}"
    )
    for agent in payload["agents"]:
        print(
            "{agent}: status={status} total={total} failed={failed} "
            "pass_rate={pass_rate}".format(**agent)
        )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
