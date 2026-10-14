"""客户长上下文会话摘要 smoke 检查。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.service import chat_context as chat_context_module  # noqa: E402
from app.models.knowledge import KnowledgeEntry  # noqa: E402
from app.service.agents.customer.prompts import (  # noqa: E402
    SESSION_SUMMARY_SECTION_TITLE,
)
from app.service.chat_context import (  # noqa: E402
    prepare_chat_context,
)
from app.service.chat_context_budget import (  # noqa: E402
    BUDGET_PRESSURE_LEVEL_CRITICAL,
    build_chat_context_budget_snapshot,
    record_tool_context_budget_delta,
)
from app.service.llm.intent import IntentType  # noqa: E402

LONG_HISTORY_REPEAT_COUNT = 4200
SUMMARY_TEXT = "客户早前说明想订低糖生日蛋糕，配送时间和是否需要蜡烛待确认。"
RECENT_USER_MESSAGE = "最近客户追问：今天下午四点前还能不能送到？"
RECENT_ASSISTANT_MESSAGE = "最近客服回复：需要以配送工具和门店排期为准。"
TOOL_RESULT_REPEAT_COUNT = 9000


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


class SmokeKnowledgeRetriever:
    """不触发外部检索的最小知识检索桩。"""

    def __init__(self) -> None:
        self.search_calls: list[tuple[str, int]] = []

    async def search(self, query: str, limit: int = 8) -> list[KnowledgeEntry]:
        self.search_calls.append((query, limit))
        return [
            KnowledgeEntry(
                id=1,
                title="配送规则",
                content="同城配送需以门店排期和配送工具结果为准。",
            )
        ]

    async def search_keyword_only(
        self, query: str, limit: int = 8
    ) -> list[KnowledgeEntry]:
        return await self.search(query, limit)


async def run_smoke_checks() -> list[SmokeCheck]:
    original_rewrite_query = chat_context_module.rewrite_query
    chat_context_module.rewrite_query = _identity_rewrite_query
    try:
        checks = await _run_context_checks()
        checks.extend(_run_tool_pressure_checks())
        return checks
    finally:
        chat_context_module.rewrite_query = original_rewrite_query


async def _identity_rewrite_query(user_query: str, history: str = "") -> str:
    return user_query


async def _run_context_checks() -> list[SmokeCheck]:
    history = _build_long_history()
    knowledge = SmokeKnowledgeRetriever()
    chat_context = await prepare_chat_context(
        knowledge=knowledge,
        user_query="配送还来得及吗",
        history_text="用户：配送还来得及吗",
        intent=IntentType.PRODUCT_CONSULTATION,
        history=history,
        conversation_summary_text=SUMMARY_TEXT,
    )
    system_prompt = str(chat_context.messages[0]["content"])
    history_messages = chat_context.messages[1:]
    context_budget = chat_context.context_budget
    return [
        _check_contains(
            "summary.section_present",
            system_prompt,
            SESSION_SUMMARY_SECTION_TITLE,
        ),
        _check_contains("summary.content_present", system_prompt, "低糖生日蛋糕"),
        _check_contains(
            "summary.fact_boundary_present",
            system_prompt,
            "订单、库存、配送、价格仍以工具和知识库为准",
        ),
        _check_bool(
            "history.recent_user_preserved",
            any(
                message.get("content") == RECENT_USER_MESSAGE
                for message in history_messages
            ),
            "recent user message missing",
        ),
        _check_bool(
            "history.recent_assistant_preserved",
            any(
                message.get("content") == RECENT_ASSISTANT_MESSAGE
                for message in history_messages
            ),
            "recent assistant message missing",
        ),
        _check_bool(
            "history.summary_not_in_history",
            all(
                "低糖生日蛋糕" not in str(message.get("content", ""))
                for message in history_messages
            ),
            "summary leaked into history messages",
        ),
        _check_bool(
            "budget.summary_present",
            bool(context_budget and context_budget.conversation_summary_present),
            "context budget did not mark summary present",
        ),
        _check_bool(
            "budget.history_pressure_candidate",
            bool(context_budget and context_budget.needs_session_summary_candidate),
            "long history did not mark summary candidate",
        ),
        _check_bool(
            "retrieval.query_stable",
            knowledge.search_calls == [("配送还来得及吗", 8)],
            f"unexpected search calls: {knowledge.search_calls!r}",
        ),
    ]


def _build_long_history() -> list[dict[str, str]]:
    long_context = (
        "长对话背景：" + "客户多轮咨询配送和售后。" * LONG_HISTORY_REPEAT_COUNT
    )
    return [
        {"role": "user", "content": long_context},
        {"role": "assistant", "content": "已说明需要继续确认配送排期。"},
        {"role": "user", "content": RECENT_USER_MESSAGE},
        {"role": "assistant", "content": RECENT_ASSISTANT_MESSAGE},
    ]


def _run_tool_pressure_checks() -> list[SmokeCheck]:
    context_budget = build_chat_context_budget_snapshot(
        system_prompt="system",
        history=[{"role": "user", "content": "短消息"}],
        knowledge_entries=[],
        knowledge_entry_limit=8,
        customer_profile=None,
    ).to_dict()
    timing: dict[str, object] = {"context_budget": context_budget}
    record_tool_context_budget_delta(
        timing,
        [{"role": "tool", "content": "工具结果很长" * TOOL_RESULT_REPEAT_COUNT}],
    )
    refreshed_budget = timing["context_budget"]
    if not isinstance(refreshed_budget, dict):
        return [SmokeCheck("tool_pressure.context_budget_dict", False)]
    return [
        _check_bool(
            "tool_pressure.critical",
            refreshed_budget.get("budget_pressure_level")
            == BUDGET_PRESSURE_LEVEL_CRITICAL,
            f"level={refreshed_budget.get('budget_pressure_level')!r}",
        ),
        _check_bool(
            "tool_pressure.no_summary_candidate",
            refreshed_budget.get("needs_session_summary_candidate") is False,
            "tool pressure incorrectly marked summary candidate",
        ),
    ]


def _check_bool(name: str, passed: bool, failure_detail: str) -> SmokeCheck:
    return SmokeCheck(name, passed, "" if passed else failure_detail)


def _check_contains(name: str, text: str, expected: str) -> SmokeCheck:
    return SmokeCheck(
        name,
        expected in text,
        "" if expected in text else f"missing: {expected}",
    )


def build_json_report(checks: list[SmokeCheck]) -> dict[str, object]:
    failed_checks = [check for check in checks if not check.passed]
    return {
        "status": "passed" if not failed_checks else "failed",
        "metadata": {
            "generated_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "project_root": str(ROOT_DIR),
            "llm": "disabled",
        },
        "total": len(checks),
        "failed": len(failed_checks),
        "checks": [check.to_dict() for check in checks],
        "failed_names": [check.name for check in failed_checks],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check customer long-context summary prompt behavior"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    checks = await run_smoke_checks()
    report = build_json_report(checks)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"customer_long_context_summary_smoke status={report['status']}")
        for check in checks:
            mark = "OK" if check.passed else "FAIL"
            print(f"[{mark}] {check.name} {check.detail}".rstrip())
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
