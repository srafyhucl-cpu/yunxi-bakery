"""生成本地 Agent trace 探针报告。"""

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
from app.models.employee_agent import AgentIntent, AgentPlan  # noqa: E402
from app.models.session import Session  # noqa: E402
from app.service.agents.customer.contracts import (  # noqa: E402
    CustomerGraphDependencies,
    CustomerGraphRequest,
)
from app.service.agents.customer.model import CustomerModelResult  # noqa: E402
from app.service.agents.customer.service import CustomerAgentGraphService  # noqa: E402
from app.service.agents.employee.nodes import EmployeeGraphDependencies  # noqa: E402
from app.service.agents.employee.service import EmployeeAgentGraphService  # noqa: E402

DEFAULT_OUTPUT_DIR = ROOT_DIR / "reports" / "agent-traces"


class _ProbeSessionManager:
    async def build_context(self, session_id: str) -> list[dict[str, str]]:
        return [{"role": "user", "content": f"trace probe session {session_id}"}]


class _ProbeKnowledgeRetriever:
    async def search(self, query: str, limit: int = 8) -> list:
        return []

    async def search_keyword_only(self, query: str, limit: int = 8) -> list:
        return []


class _ProbePlanner:
    async def plan(self, query: str) -> AgentPlan:
        return AgentPlan(
            intent=AgentIntent.PRODUCT_QUERY,
            tools=("product_lookup",),
        )


class _ProbeBusinessToolService:
    async def lookup_orders(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "订单 trace probe"}

    async def lookup_products(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "商品 trace probe｜库存 1"}

    async def answer_knowledge(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "知识 trace probe"}


class _ProbeOpsToolService:
    async def lookup_customer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "客户 trace probe"}

    async def summarize_group_campaign(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {"ok": True, "result": "客户群 trace probe"}

    async def list_pending_handoffs(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "待人工 trace probe"}


class _ProbeStatusToolService:
    async def summarize_ops(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "经营 trace probe"}

    async def summarize_integrations(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "同步 trace probe"}

    async def summarize_offline_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "离线复盘 trace probe"}


async def main_async(output_path: Path | None = None) -> Path:
    traces = [
        await _run_customer_trace_probe(),
        await _run_employee_trace_probe(),
    ]
    path = output_path or _default_output_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "metadata": {
                    "generated_at": _utc_now(),
                    "app_version": APP_VERSION,
                    "source": "probe_agent_traces",
                },
                "traces": [trace.to_dict() for trace in traces],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate local agent trace probes")
    parser.add_argument("--output", type=Path, help="输出 trace JSON 路径")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    output_path = asyncio.run(main_async(args.output))
    print(f"agent_trace_probe output={output_path}")
    return 0


async def _identity_rewrite_query(query: str, history: str = "") -> str:
    """探针用假查询改写，避免真实外部 LLM 调用。"""

    return query


async def _run_customer_trace_probe():
    from app.service.agents.customer import nodes as customer_nodes
    from app.service import chat_context

    original_request = customer_nodes.request_customer_model_with_tools
    original_build_tools = customer_nodes.build_tools
    original_rewrite_query = chat_context.rewrite_query
    customer_nodes.request_customer_model_with_tools = _fake_customer_model_request
    customer_nodes.build_tools = lambda *_args, **_kwargs: []
    chat_context.rewrite_query = _identity_rewrite_query
    try:
        service = CustomerAgentGraphService(
            CustomerGraphDependencies(
                session_mgr=_ProbeSessionManager(),
                knowledge=_ProbeKnowledgeRetriever(),
                transfer_mgr=object(),
                session_repo=object(),
                youzan_client=object(),
                fallback_reply="客户 trace probe 兜底",
                timeout_reply="客户 trace probe 超时",
                failure_alerter=_probe_alerter,
            )
        )
        _reply, trace_run = await service.answer_with_trace(
            CustomerGraphRequest(
                session=Session(
                    id="trace-probe-customer",
                    channel="probe",
                    user_id="probe-user",
                ),
                user_query="trace probe 商品咨询",
                timing={},
            )
        )
        return trace_run
    finally:
        customer_nodes.request_customer_model_with_tools = original_request
        customer_nodes.build_tools = original_build_tools
        chat_context.rewrite_query = original_rewrite_query


async def _run_employee_trace_probe():
    service = EmployeeAgentGraphService(
        EmployeeGraphDependencies(
            business_tool_service=_ProbeBusinessToolService(),
            ops_tool_service=_ProbeOpsToolService(),
            status_tool_service=_ProbeStatusToolService(),
            planner=_ProbePlanner(),
        )
    )
    _reply, trace_run = await service.answer_with_trace("trace probe 商品库存")
    return trace_run


async def _fake_customer_model_request(_context: Any) -> CustomerModelResult:
    return CustomerModelResult(
        message=SimpleNamespace(
            content="客户 trace probe 回复",
            tool_calls=[],
            response_metadata={"finish_reason": "stop"},
        ),
        finish_reason="stop",
        model_name="trace-probe-model",
        first_llm_started_at=1.0,
    )


async def _probe_alerter(message: str) -> None:
    raise AssertionError(message)


def _default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"agent-traces-{timestamp}.json"


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
