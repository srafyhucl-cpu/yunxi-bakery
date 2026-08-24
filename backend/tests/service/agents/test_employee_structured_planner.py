"""员工助手 LangChain structured planner 测试。"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from app.models.employee_agent import AgentIntent, AnswerStyle, OrderQueryKind
from app.service.agents.employee import structured_planner
from app.service.agents.employee.structured_planner import (
    EmployeeStructuredPlan,
    request_employee_plan_with_langchain,
)
from app.service.wecom.employee_agent_capabilities import AgentCapabilityCard


class _FakeStructuredModel:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.config: dict[str, Any] = {}

    async def ainvoke(
        self,
        messages: list[tuple[str, str]],
        config: dict[str, Any],
    ) -> EmployeeStructuredPlan:
        self.messages = messages
        self.config = config
        return EmployeeStructuredPlan(
            intent="order_query",
            tools=["order_dynamic_query"],
            queryPlan={
                "kind": "summary",
                "dateFrom": "2026-07-09",
                "dateTo": "2026-07-09",
                "statuses": ["WAIT_SELLER_SEND_GOODS"],
                "limit": 8,
            },
            answerStyle="summary",
        )


class _FakeChatModel:
    def __init__(self, structured_model: _FakeStructuredModel) -> None:
        self.structured_model = structured_model
        self.schema: Any = None

    def with_structured_output(self, schema: Any) -> _FakeStructuredModel:
        self.schema = schema
        return self.structured_model


@pytest.mark.asyncio
async def test_request_employee_plan_with_langchain_returns_safe_agent_plan(
    monkeypatch,
) -> None:
    structured_model = _FakeStructuredModel()
    chat_model = _FakeChatModel(structured_model)
    monkeypatch.setattr(
        structured_planner,
        "get_langchain_chat_model",
        lambda **_kwargs: chat_model,
    )
    capabilities = [
        AgentCapabilityCard(
            name="order_dynamic_query",
            intent="order_query",
            description="查询订单",
            examples=("今天多少订单",),
            keywords=("订单",),
        )
    ]

    plan = await request_employee_plan_with_langchain(
        "今天多少订单",
        capabilities,
    )

    assert chat_model.schema is EmployeeStructuredPlan
    assert structured_model.messages[0][0] == "system"
    assert "order_dynamic_query" in structured_model.messages[1][1]
    assert structured_model.config["run_name"] == "employee_structured_planner"
    assert plan is not None
    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.answer_style == AnswerStyle.SUMMARY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.SUMMARY
    assert plan.query_plan.limit == 8


def test_employee_structured_planner_import_does_not_load_langchain_runtime() -> None:
    project_root = Path(__file__).resolve().parents[3]
    command = (
        "import sys; "
        "import app.service.agents.employee.structured_planner; "
        "raise SystemExit(1 if 'langchain_openai' in sys.modules else 0)"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=project_root,
        check=False,
    )

    assert result.returncode == 0
