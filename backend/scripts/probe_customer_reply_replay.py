"""生成客户机器人回复回放输入。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from app.models.session import Session  # noqa: E402
from app.service.agents.customer.contracts import (  # noqa: E402
    CustomerGraphDependencies,
    CustomerGraphRequest,
)
from app.service.agents.customer.model import CustomerModelResult  # noqa: E402
from app.service.agents.customer.service import CustomerAgentGraphService  # noqa: E402
from app.service.llm.intent import IntentType  # noqa: E402
from scripts.check_customer_rag_golden_cases import (  # noqa: E402
    FIXTURE_PATH,
    load_fixture,
)

DEFAULT_OUTPUT_DIR = ROOT_DIR / "reports" / "agent-eval"
SAFE_GRAPH_REPLY = (
    "这类问题需要结合订单、库存或门店实时情况确认，我会先帮您整理信息并转人工处理。"
)


class _ReplaySessionManager:
    async def build_context(self, session_id: str) -> list[dict[str, str]]:
        return [{"role": "user", "content": f"reply replay session {session_id}"}]


class _ReplayKnowledgeRetriever:
    async def search(self, query: str, limit: int = 8) -> list:
        return []

    async def search_keyword_only(self, query: str, limit: int = 8) -> list:
        return []


async def main_async(
    output_path: Path | None = None,
    fixture_path: Path = FIXTURE_PATH,
    case_ids: tuple[str, ...] = (),
) -> Path:
    cases = _load_sensitive_cases(fixture_path, case_ids)
    replies = await _run_customer_graph_replies(cases)
    path = output_path or _default_output_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "metadata": {
                    "generated_at": _utc_now(),
                    "app_version": APP_VERSION,
                    "source": "probe_customer_reply_replay",
                    "fixture": str(fixture_path),
                    "llm": "fake",
                },
                "replies": replies,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _load_sensitive_cases(
    fixture_path: Path,
    case_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    selected_ids = set(case_ids)
    payload = load_fixture(fixture_path)
    return [
        case
        for case in payload.get("cases", [])
        if isinstance(case, dict)
        and case.get("sensitive_scenarios")
        and (not selected_ids or str(case.get("id", "")) in selected_ids)
    ]


async def _identity_rewrite_query(query: str, history: str = "") -> str:
    """探针用假查询改写，避免真实外部 LLM 调用。"""

    return query


async def _run_customer_graph_replies(
    cases: list[dict[str, Any]],
) -> list[dict[str, object]]:
    from app.service.agents.customer import nodes as customer_nodes
    from app.service import chat_context

    original_request = customer_nodes.request_customer_model_with_tools
    original_build_tools = customer_nodes.build_tools
    original_rewrite_query = chat_context.rewrite_query
    customer_nodes.request_customer_model_with_tools = _fake_customer_model_request
    customer_nodes.build_tools = lambda *_args, **_kwargs: []
    chat_context.rewrite_query = _identity_rewrite_query
    try:
        service = CustomerAgentGraphService(_build_dependencies())
        replies: list[dict[str, object]] = []
        for case in cases:
            reply, _trace_run = await service.answer_with_trace(
                CustomerGraphRequest(
                    session=Session(
                        id=f"reply-replay-{case.get('id')}",
                        channel="reply_replay",
                        user_id="reply-replay-user",
                    ),
                    user_query=str(case.get("query", "")),
                    intent=IntentType.PRODUCT_CONSULTATION,
                    timing={},
                )
            )
            replies.append(
                {
                    "case_id": str(case.get("id", "")),
                    "query": str(case.get("query", "")),
                    "reply": reply,
                    "source": "customer_graph_fake_model",
                }
            )
        return replies
    finally:
        customer_nodes.request_customer_model_with_tools = original_request
        customer_nodes.build_tools = original_build_tools
        chat_context.rewrite_query = original_rewrite_query


def _build_dependencies() -> CustomerGraphDependencies:
    return CustomerGraphDependencies(
        session_mgr=_ReplaySessionManager(),
        knowledge=_ReplayKnowledgeRetriever(),
        transfer_mgr=object(),
        session_repo=object(),
        youzan_client=object(),
        fallback_reply="客户回复回放兜底",
        timeout_reply="客户回复回放超时",
        failure_alerter=_probe_alerter,
    )


async def _fake_customer_model_request(_context: Any) -> CustomerModelResult:
    return CustomerModelResult(
        message=SimpleNamespace(
            content=SAFE_GRAPH_REPLY,
            tool_calls=[],
            response_metadata={"finish_reason": "stop"},
        ),
        finish_reason="stop",
        model_name="reply-replay-fake-model",
        first_llm_started_at=1.0,
    )


async def _probe_alerter(message: str) -> None:
    raise AssertionError(message)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate customer reply replay JSON")
    parser.add_argument("--output", type=Path, help="输出 replies JSON 路径")
    parser.add_argument(
        "--fixture",
        default=str(FIXTURE_PATH),
        help="客户 eval fixture",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="只生成指定 case_id，可重复传入",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    output_path = asyncio.run(
        main_async(
            output_path=args.output,
            fixture_path=Path(args.fixture),
            case_ids=tuple(args.case_id),
        )
    )
    print(f"customer_reply_replay_probe output={output_path}")
    return 0


def _default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"customer-reply-replay-{timestamp}.json"


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
