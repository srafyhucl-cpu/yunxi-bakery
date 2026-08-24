"""企微员工助手非订单规则计划。"""

from __future__ import annotations

import re

from app.models.employee_agent import AgentIntent, AgentPlan, AnswerStyle

CAMPAIGN_ID_PATTERN = re.compile(r"campaign(?:Id|ID|id)?[:：=\s]+([A-Za-z0-9_-]+)")


def build_ops_rule_plan(
    query: str,
    capability_names: set[str],
) -> AgentPlan | None:
    """按确定性规则生成客户、群运营和复盘计划。"""
    if _looks_like_customer_query(query, capability_names):
        return AgentPlan(
            intent=AgentIntent.OPS_QUERY,
            tools=("customer_lookup",),
            answer_style=AnswerStyle.SUMMARY,
        )
    if _looks_like_group_campaign_query(query, capability_names):
        return AgentPlan(
            intent=AgentIntent.OPS_QUERY,
            tools=("group_campaign_summary",),
            answer_style=AnswerStyle.SUMMARY,
        )
    if _looks_like_integration_status_query(query, capability_names):
        return AgentPlan(
            intent=AgentIntent.OPS_QUERY,
            tools=("integration_status",),
            answer_style=AnswerStyle.SUMMARY,
        )
    if _looks_like_offline_review_query(query, capability_names):
        return AgentPlan(
            intent=AgentIntent.OPS_QUERY,
            tools=("offline_review_summary",),
            answer_style=AnswerStyle.SUMMARY,
        )
    return None


def extract_campaign_id(text: str) -> str:
    """从员工原话中提取客户群活动 ID。"""
    match = CAMPAIGN_ID_PATTERN.search(text)
    return match.group(1) if match else ""


def _looks_like_customer_query(query: str, capability_names: set[str]) -> bool:
    return "customer_lookup" in capability_names and any(
        word in query for word in ("客户", "地址线索", "收货地址", "地址")
    )


def _looks_like_group_campaign_query(
    query: str,
    capability_names: set[str],
) -> bool:
    return "group_campaign_summary" in capability_names and bool(
        extract_campaign_id(query)
    )


def _looks_like_integration_status_query(
    query: str,
    capability_names: set[str],
) -> bool:
    return "integration_status" in capability_names and any(
        word in query
        for word in (
            "同步失败",
            "webhook",
            "Webhook",
            "回调失败",
            "回调异常",
            "失败记录",
        )
    )


def _looks_like_offline_review_query(
    query: str,
    capability_names: set[str],
) -> bool:
    return "offline_review_summary" in capability_names and any(
        word in query for word in ("离线复盘", "昨晚复盘", "夜间复盘", "复盘结果")
    )
