"""企微员工助手订单规则计划。"""

from __future__ import annotations

from datetime import date

from app.models.employee_agent import (
    AgentIntent,
    AgentPlan,
    AnswerStyle,
    OrderQueryKind,
)
from app.service.wecom.employee_agent_capabilities import AgentCapabilityCard
from app.service.wecom.employee_agent_non_order_plan import (
    build_non_order_agent_plan,
    build_product_knowledge_agent_plan,
)
from app.service.wecom.employee_agent_order_query import (
    answer_style_for_order_kind,
    build_order_query_plan,
    has_exact_order_no,
    looks_like_inventory_query,
    looks_like_order_knowledge_query,
    looks_like_order_query,
    looks_like_order_policy_query,
    resolve_order_kind,
)
from app.service.wecom.employee_agent_order_predicates import (
    has_customer_history_intent,
)
from app.service.wecom.employee_agent_ops_plan import build_ops_rule_plan


def build_rule_plan(
    query: str,
    capabilities: list[AgentCapabilityCard],
    today: date,
) -> AgentPlan:
    """按确定性规则生成员工助手计划。"""
    if not query.strip():
        return AgentPlan(intent=AgentIntent.UNSUPPORTED)
    if has_exact_order_no(query):
        return _build_exact_order_plan(query, today)
    capability_names = _capability_names_for_rule_plan(query, capabilities)
    has_order = "order_dynamic_query" in capability_names or looks_like_order_query(
        query
    )
    if (
        has_order
        and "product_lookup" in capability_names
        and looks_like_inventory_query(query)
    ):
        return _build_order_agent_plan(
            query,
            today,
            intent=AgentIntent.MULTI_TOOL,
            tools=("order_dynamic_query", "product_lookup"),
            answer_style=AnswerStyle.SUMMARY,
        )
    if (
        has_order
        and "knowledge_answer" in capability_names
        and looks_like_order_knowledge_query(query)
    ):
        return _build_order_agent_plan(
            query,
            today,
            intent=AgentIntent.MULTI_TOOL,
            tools=("order_dynamic_query", "knowledge_answer"),
            answer_style=AnswerStyle.SUMMARY,
        )
    if has_order:
        return _build_order_agent_plan(
            query,
            today,
            intent=AgentIntent.ORDER_QUERY,
            tools=("order_dynamic_query",),
        )
    product_knowledge_plan = build_product_knowledge_agent_plan(
        query,
        capability_names,
    )
    if product_knowledge_plan is not None:
        return product_knowledge_plan
    ops_plan = build_ops_rule_plan(query, capability_names)
    if ops_plan is not None:
        return ops_plan
    return build_non_order_agent_plan(query, capability_names, has_order)


def _capability_names_for_rule_plan(
    query: str,
    capabilities: list[AgentCapabilityCard],
) -> set[str]:
    capability_names = {card.name for card in capabilities}
    if looks_like_order_policy_query(query):
        capability_names.discard("order_dynamic_query")
    return capability_names


def _build_exact_order_plan(query: str, today: date) -> AgentPlan:
    if has_customer_history_intent(query):
        return AgentPlan(
            intent=AgentIntent.ORDER_QUERY,
            tools=("order_dynamic_query",),
            query_plan=build_order_query_plan(query, today, OrderQueryKind.LIST),
            answer_style=AnswerStyle.LIST,
        )
    return AgentPlan(
        intent=AgentIntent.ORDER_QUERY,
        tools=("order_dynamic_query",),
        query_plan=build_order_query_plan(query, today, OrderQueryKind.DETAIL),
        answer_style=AnswerStyle.DETAIL,
    )


def _build_order_agent_plan(
    query: str,
    today: date,
    *,
    intent: AgentIntent,
    tools: tuple[str, ...],
    answer_style: AnswerStyle | None = None,
) -> AgentPlan:
    order_kind = resolve_order_kind(query)
    return AgentPlan(
        intent=intent,
        tools=tools,
        query_plan=build_order_query_plan(query, today, order_kind),
        answer_style=answer_style or answer_style_for_order_kind(order_kind),
    )
