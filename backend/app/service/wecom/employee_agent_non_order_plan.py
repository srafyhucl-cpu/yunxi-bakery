"""企微员工助手非订单规则计划。"""

from __future__ import annotations

from app.models.employee_agent import AgentIntent, AgentPlan, AnswerStyle
from app.service.wecom.employee_agent_product_query import (
    looks_like_product_knowledge_query,
)


def build_product_knowledge_agent_plan(
    query: str,
    capability_names: set[str],
) -> AgentPlan | None:
    """生成商品实时数据加知识库话术的组合计划。"""
    if (
        "product_lookup" in capability_names
        and "knowledge_answer" in capability_names
        and looks_like_product_knowledge_query(query)
    ):
        return AgentPlan(
            intent=AgentIntent.MULTI_TOOL,
            tools=("product_lookup", "knowledge_answer"),
            answer_style=AnswerStyle.SUMMARY,
        )
    return None


def build_non_order_agent_plan(
    query: str,
    capability_names: set[str],
    has_order: bool,
) -> AgentPlan:
    """生成不依赖订单动态查询的规则计划。"""
    product_knowledge_plan = build_product_knowledge_agent_plan(
        query,
        capability_names,
    )
    if product_knowledge_plan is not None:
        return product_knowledge_plan
    if "product_lookup" in capability_names and not has_order:
        return AgentPlan(
            intent=AgentIntent.PRODUCT_QUERY,
            tools=("product_lookup",),
            answer_style=AnswerStyle.SUMMARY,
        )
    if capability_names & {"ops_summary", "handoff_pending", "integration_status"}:
        return AgentPlan(
            intent=AgentIntent.OPS_QUERY,
            tools=tuple(sorted(capability_names)) or ("ops_summary",),
            answer_style=AnswerStyle.SUMMARY,
        )
    if "knowledge_answer" in capability_names:
        return AgentPlan(
            intent=AgentIntent.KNOWLEDGE_ANSWER,
            tools=("knowledge_answer",),
            answer_style=AnswerStyle.SUMMARY,
        )
    return AgentPlan(intent=AgentIntent.UNSUPPORTED)
