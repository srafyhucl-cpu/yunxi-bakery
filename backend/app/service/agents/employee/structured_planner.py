"""员工助手 LangChain structured output planner。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.employee_agent import (
    AgentIntent,
    AgentPlan,
    AnswerStyle,
    OrderQueryKind,
    OrderQueryPlan,
)
from app.service.agents.employee.prompts import build_employee_planner_messages
from app.service.agents.llm import get_langchain_chat_model
from app.service.agents.observability import get_agent_tracing_config
from app.service.privacy_redaction import redact_external_text
from app.service.wecom.employee_agent_capabilities import AgentCapabilityCard
from app.service.wecom.employee_agent_order_query import extract_limit_from_value


class EmployeeStructuredOrderPlan(BaseModel):
    """员工助手订单查询计划 schema。"""

    model_config = ConfigDict(populate_by_name=True)

    kind: str = "list"
    date_from: str = Field(default="", alias="dateFrom")
    date_to: str = Field(default="", alias="dateTo")
    date_field: str = Field(default="order_time", alias="dateField")
    statuses: list[str] = Field(default_factory=list)
    keyword: str = ""
    needs_missing_logistics: bool = Field(
        default=False,
        alias="needsMissingLogistics",
    )
    needs_refund: bool = Field(default=False, alias="needsRefund")
    needs_fulfillment_risk: bool = Field(
        default=False,
        alias="needsFulfillmentRisk",
    )
    delivery_time_start: str = Field(default="", alias="deliveryTimeStart")
    delivery_time_end: str = Field(default="", alias="deliveryTimeEnd")
    aggregate_by: str = Field(default="", alias="aggregateBy")
    sort_by: str = Field(default="latest", alias="sortBy")
    limit: int = 5


class EmployeeStructuredPlan(BaseModel):
    """员工助手结构化计划 schema。"""

    model_config = ConfigDict(populate_by_name=True)

    intent: str = "unsupported"
    tools: list[str] = Field(default_factory=list)
    query_plan: EmployeeStructuredOrderPlan | None = Field(
        default=None,
        alias="queryPlan",
    )
    answer_style: str = Field(default="summary", alias="answerStyle")


async def request_employee_plan_with_langchain(
    query: str,
    capabilities: list[AgentCapabilityCard],
) -> AgentPlan | None:
    """通过 LangChain structured output 请求员工助手计划。"""
    model = get_langchain_chat_model(provider="mimo", temperature=0.0)
    structured_model = model.with_structured_output(EmployeeStructuredPlan)
    result = await structured_model.ainvoke(
        build_employee_planner_messages(redact_external_text(query), capabilities),
        config=get_agent_tracing_config().to_runnable_config(
            run_name="employee_structured_planner",
            tags=("employee", "planner"),
            metadata={"capability_count": len(capabilities)},
        ),
    )
    structured_plan = _coerce_structured_plan(result)
    if structured_plan is None:
        return None
    return _to_agent_plan(structured_plan)


def _coerce_structured_plan(result: Any) -> EmployeeStructuredPlan | None:
    if isinstance(result, EmployeeStructuredPlan):
        return result
    if isinstance(result, dict):
        return EmployeeStructuredPlan.model_validate(result)
    return None


def _to_agent_plan(plan: EmployeeStructuredPlan) -> AgentPlan:
    return AgentPlan(
        intent=_safe_enum(AgentIntent, plan.intent, AgentIntent.UNSUPPORTED),
        tools=tuple(tool for tool in plan.tools if isinstance(tool, str)),
        query_plan=_to_order_query_plan(plan.query_plan),
        answer_style=_safe_enum(
            AnswerStyle,
            plan.answer_style,
            AnswerStyle.SUMMARY,
        ),
    )


def _to_order_query_plan(
    plan: EmployeeStructuredOrderPlan | None,
) -> OrderQueryPlan | None:
    if plan is None:
        return None
    date_field = (
        plan.date_field
        if plan.date_field
        in {
            "order_time",
            "delivery_time",
        }
        else "order_time"
    )
    return OrderQueryPlan(
        kind=_safe_enum(OrderQueryKind, plan.kind, OrderQueryKind.LIST),
        date_from=plan.date_from,
        date_to=plan.date_to,
        date_field=date_field,
        statuses=tuple(status for status in plan.statuses if isinstance(status, str)),
        keyword=plan.keyword,
        needs_missing_logistics=plan.needs_missing_logistics,
        needs_refund=plan.needs_refund,
        needs_fulfillment_risk=plan.needs_fulfillment_risk,
        delivery_time_start=plan.delivery_time_start,
        delivery_time_end=plan.delivery_time_end,
        aggregate_by=plan.aggregate_by,
        sort_by=plan.sort_by,
        limit=extract_limit_from_value(plan.limit),
    )


def _safe_enum(enum_type: Any, value: Any, fallback: Any) -> Any:
    try:
        return enum_type(str(value))
    except ValueError:
        return fallback
