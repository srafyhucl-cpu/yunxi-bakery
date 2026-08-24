"""员工助手 Agent 结构化计划模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentIntent(str, Enum):
    ORDER_QUERY = "order_query"
    PRODUCT_QUERY = "product_query"
    KNOWLEDGE_ANSWER = "knowledge_answer"
    OPS_QUERY = "ops_query"
    MULTI_TOOL = "multi_tool"
    UNSUPPORTED = "unsupported"


class AnswerStyle(str, Enum):
    SUMMARY = "summary"
    LIST = "list"
    DETAIL = "detail"
    ACTION_ITEMS = "action_items"


class OrderQueryKind(str, Enum):
    SUMMARY = "summary"
    LIST = "list"
    DETAIL = "detail"
    TOP_PRODUCTS = "top_products"
    ACTION_ITEMS = "action_items"


@dataclass(frozen=True)
class OrderQueryPlan:
    """订单动态查询计划，由 Agent 生成、仓库层白名单执行。"""

    kind: OrderQueryKind = OrderQueryKind.LIST
    buyer_id: str = ""
    date_from: str = ""
    date_to: str = ""
    date_field: str = "order_time"
    statuses: tuple[str, ...] = ()
    keyword: str = ""
    needs_missing_logistics: bool = False
    needs_refund: bool = False
    needs_fulfillment_risk: bool = False
    delivery_time_start: str = ""
    delivery_time_end: str = ""
    aggregate_by: str = ""
    sort_by: str = "latest"
    limit: int = 5


@dataclass(frozen=True)
class AgentPlan:
    """员工助手一次回答的结构化执行计划。"""

    intent: AgentIntent
    tools: tuple[str, ...] = ()
    query_plan: OrderQueryPlan | None = None
    answer_style: AnswerStyle = AnswerStyle.SUMMARY


@dataclass(frozen=True)
class ToolResult:
    """员工助手工具执行后的统一结果。"""

    ok: bool
    summary: str
    items: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    next_action: str = ""
