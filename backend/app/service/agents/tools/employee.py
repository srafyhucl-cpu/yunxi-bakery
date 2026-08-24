"""员工助手 LangChain 工具。"""

from dataclasses import dataclass
from typing import Any
import json

from pydantic import BaseModel, Field


DEFAULT_EMPLOYEE_TOOL_LIMIT = 5
EMPLOYEE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "order_dynamic_query",
        "product_lookup",
        "knowledge_answer",
        "ops_summary",
        "integration_status",
        "handoff_pending",
        "customer_lookup",
        "group_campaign_summary",
        "offline_review_summary",
    }
)
EMPLOYEE_OPS_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "ops_summary",
        "integration_status",
        "handoff_pending",
        "customer_lookup",
        "group_campaign_summary",
        "offline_review_summary",
    }
)


@dataclass(frozen=True)
class EmployeeToolContext:
    """员工助手工具运行依赖。"""

    business_tool_service: Any = None
    ops_tool_service: Any = None
    status_tool_service: Any = None


class EmployeeQueryArgs(BaseModel):
    query: str = Field(description="员工查询文本")
    limit: int = Field(default=DEFAULT_EMPLOYEE_TOOL_LIMIT, description="返回条数上限")


class EmployeeKnowledgeArgs(BaseModel):
    question: str = Field(description="要查询的规则、话术或问题")
    limit: int = Field(default=DEFAULT_EMPLOYEE_TOOL_LIMIT, description="返回条数上限")


class GroupCampaignSummaryArgs(BaseModel):
    campaign_id: str = Field(description="客户群活动批次 ID")
    limit: int = Field(default=DEFAULT_EMPLOYEE_TOOL_LIMIT, description="返回条数上限")


class EmployeeNoQueryArgs(BaseModel):
    limit: int = Field(default=DEFAULT_EMPLOYEE_TOOL_LIMIT, description="返回条数上限")


def build_employee_tools(context: EmployeeToolContext) -> list[Any]:
    """构造员工助手 LangChain 工具列表。"""
    from langchain_core.tools import StructuredTool

    return [
        _build_order_tool(context, StructuredTool),
        _build_product_tool(context, StructuredTool),
        _build_knowledge_tool(context, StructuredTool),
        _build_ops_tool(context, StructuredTool),
        _build_integration_tool(context, StructuredTool),
        _build_handoff_tool(context, StructuredTool),
        _build_customer_tool(context, StructuredTool),
        _build_group_campaign_tool(context, StructuredTool),
        _build_offline_review_tool(context, StructuredTool),
    ]


def _build_order_tool(context: EmployeeToolContext, structured_tool: Any) -> Any:
    async def order_dynamic_query_tool(
        query: str,
        limit: int = DEFAULT_EMPLOYEE_TOOL_LIMIT,
    ) -> str:
        service = context.business_tool_service
        if service is None:
            return _dump_unavailable("order_dynamic_query", "订单动态查询")
        return _dump_response(await service.lookup_orders(_query_payload(query, limit)))

    return structured_tool.from_function(
        coroutine=order_dynamic_query_tool,
        name="order_dynamic_query",
        description="查询订单、今日订单、待发货、退款、履约风险和订单统计",
        args_schema=EmployeeQueryArgs,
        return_direct=True,
    )


def _build_product_tool(context: EmployeeToolContext, structured_tool: Any) -> Any:
    async def product_lookup_tool(
        query: str,
        limit: int = DEFAULT_EMPLOYEE_TOOL_LIMIT,
    ) -> str:
        service = context.business_tool_service
        if service is None:
            return _dump_unavailable("product_lookup", "商品库存查询")
        return _dump_response(
            await service.lookup_products(_query_payload(query, limit))
        )

    return structured_tool.from_function(
        coroutine=product_lookup_tool,
        name="product_lookup",
        description="查询商品价格、库存、分类和上架状态",
        args_schema=EmployeeQueryArgs,
        return_direct=True,
    )


def _build_knowledge_tool(context: EmployeeToolContext, structured_tool: Any) -> Any:
    async def knowledge_answer_tool(
        question: str,
        limit: int = DEFAULT_EMPLOYEE_TOOL_LIMIT,
    ) -> str:
        service = context.business_tool_service
        if service is None:
            return _dump_unavailable("knowledge_answer", "知识库问答")
        return _dump_response(
            await service.answer_knowledge({"question": question, "limit": limit})
        )

    return structured_tool.from_function(
        coroutine=knowledge_answer_tool,
        name="knowledge_answer",
        description="查询门店规则、配送售后话术和员工可复制回复",
        args_schema=EmployeeKnowledgeArgs,
        return_direct=True,
    )


def _build_ops_tool(context: EmployeeToolContext, structured_tool: Any) -> Any:
    async def ops_summary_tool(limit: int = DEFAULT_EMPLOYEE_TOOL_LIMIT) -> str:
        service = context.status_tool_service
        if service is None:
            return _dump_unavailable("ops_summary", "经营观察摘要")
        return _dump_response(await service.summarize_ops({"limit": limit}))

    return structured_tool.from_function(
        coroutine=ops_summary_tool,
        name="ops_summary",
        description="查询系统状态、观察台和经营观察摘要",
        args_schema=EmployeeNoQueryArgs,
        return_direct=True,
    )


def _build_integration_tool(
    context: EmployeeToolContext,
    structured_tool: Any,
) -> Any:
    async def integration_status_tool(
        query: str,
        limit: int = DEFAULT_EMPLOYEE_TOOL_LIMIT,
    ) -> str:
        service = context.status_tool_service
        if service is None:
            return _dump_unavailable("integration_status", "同步排障")
        return _dump_response(
            await service.summarize_integrations(_query_payload(query, limit))
        )

    return structured_tool.from_function(
        coroutine=integration_status_tool,
        name="integration_status",
        description="查询同步失败、Webhook 异常和第三方集成排障线索",
        args_schema=EmployeeQueryArgs,
        return_direct=True,
    )


def _build_handoff_tool(context: EmployeeToolContext, structured_tool: Any) -> Any:
    async def handoff_pending_tool(
        limit: int = DEFAULT_EMPLOYEE_TOOL_LIMIT,
    ) -> str:
        service = context.ops_tool_service
        if service is None:
            return _dump_unavailable("handoff_pending", "待人工列表")
        return _dump_response(await service.list_pending_handoffs({"limit": limit}))

    return structured_tool.from_function(
        coroutine=handoff_pending_tool,
        name="handoff_pending",
        description="查询待人工、转人工和待接单工单",
        args_schema=EmployeeNoQueryArgs,
        return_direct=True,
    )


def _build_customer_tool(context: EmployeeToolContext, structured_tool: Any) -> Any:
    async def customer_lookup_tool(
        query: str,
        limit: int = DEFAULT_EMPLOYEE_TOOL_LIMIT,
    ) -> str:
        service = context.ops_tool_service
        if service is None:
            return _dump_unavailable("customer_lookup", "客户查询")
        return _dump_response(
            await service.lookup_customer(_query_payload(query, limit))
        )

    return structured_tool.from_function(
        coroutine=customer_lookup_tool,
        name="customer_lookup",
        description="查询客户地址簿线索，返回脱敏地址预览",
        args_schema=EmployeeQueryArgs,
        return_direct=True,
    )


def _build_group_campaign_tool(
    context: EmployeeToolContext,
    structured_tool: Any,
) -> Any:
    async def group_campaign_summary_tool(
        campaign_id: str,
        limit: int = DEFAULT_EMPLOYEE_TOOL_LIMIT,
    ) -> str:
        service = context.ops_tool_service
        if service is None:
            return _dump_unavailable("group_campaign_summary", "客户群批次汇总")
        return _dump_response(
            await service.summarize_group_campaign(
                {"campaignId": campaign_id, "limit": limit}
            )
        )

    return structured_tool.from_function(
        coroutine=group_campaign_summary_tool,
        name="group_campaign_summary",
        description="按 campaignId 汇总客户群团购、预订或活动批次",
        args_schema=GroupCampaignSummaryArgs,
        return_direct=True,
    )


def _build_offline_review_tool(
    context: EmployeeToolContext,
    structured_tool: Any,
) -> Any:
    async def offline_review_summary_tool(
        limit: int = DEFAULT_EMPLOYEE_TOOL_LIMIT,
    ) -> str:
        service = context.status_tool_service
        if service is None:
            return _dump_unavailable("offline_review_summary", "离线复盘摘要")
        return _dump_response(await service.summarize_offline_review({"limit": limit}))

    return structured_tool.from_function(
        coroutine=offline_review_summary_tool,
        name="offline_review_summary",
        description="查询最近一轮离线复盘、知识缺口和跳过原因",
        args_schema=EmployeeNoQueryArgs,
        return_direct=True,
    )


def _query_payload(query: str, limit: int) -> dict[str, Any]:
    return {"query": query, "limit": limit}


def _dump_response(response: dict[str, Any]) -> str:
    return json.dumps(response, ensure_ascii=False)


def _dump_unavailable(tool_name: str, label: str) -> str:
    return json.dumps(
        {
            "tool": tool_name,
            "status": "unavailable",
            "result": f"{label}暂不可用",
        },
        ensure_ascii=False,
    )
