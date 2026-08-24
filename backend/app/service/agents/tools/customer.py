"""客户机器人 LangChain 工具。"""

from dataclasses import dataclass
from typing import Any
import json

from pydantic import BaseModel, Field

from app.models.session import Channel, Session

ORDER_OWNERSHIP_DENIAL_MESSAGE = "无法确认订单归属，请转人工客服"

ORDER_INFO_DESCRIPTION = "查询订单详细信息：状态、商品、金额、收货地址等"
PRODUCT_INFO_DESCRIPTION = (
    "实时查询指定商品的最新价格、规格和库存；当用户提供了商品ID（纯数字）或商品名称时，"
    "必须优先调用此工具而非搜索知识库"
)
LOGISTICS_INFO_DESCRIPTION = "查询物流配送进度"
TRANSFER_TO_HUMAN_DESCRIPTION = (
    "当用户要求转人工、表达不满或复杂售后问题时，转接人工客服"
)
SEARCH_KNOWLEDGE_DESCRIPTION = (
    "搜索知识库，查找店铺政策、常见问题（如退换货规则、配送说明等）；"
    "不适用于查询特定商品的实时库存和价格"
)


@dataclass(frozen=True)
class CustomerToolContext:
    """客户机器人工具运行依赖。"""

    session: Session | None = None
    knowledge_retriever: Any = None
    youzan_client: Any = None
    order_repo: Any = None
    config_repo: Any = None
    product_repo: Any = None
    knowledge_product_repo: Any = None
    analytics_repo: Any = None
    history_repo: Any = None
    embedding_searcher: Any = None
    transfer_handler: Any = None


@dataclass(frozen=True)
class CustomerOrderIdentity:
    """客户订单查询使用的可信身份范围。"""

    buyer_id: str | None = None
    outer_user_id: str | None = None


class OrderInfoArgs(BaseModel):
    order_no: str = Field(description="订单号")


class ProductInfoArgs(BaseModel):
    product_name: str = Field(default="", description="商品名称")
    product_id: str = Field(default="", description="商品ID")


class LogisticsInfoArgs(BaseModel):
    order_no: str = Field(description="订单号")


class TransferToHumanArgs(BaseModel):
    reason: str = Field(description="转人工原因")


class SearchKnowledgeArgs(BaseModel):
    query: str = Field(description="搜索关键词")


def build_customer_tools(context: CustomerToolContext) -> list[Any]:
    """构造客户机器人 LangChain 工具列表。"""
    from langchain_core.tools import StructuredTool

    return [
        _build_order_info_tool(context, StructuredTool),
        _build_product_info_tool(context, StructuredTool),
        _build_logistics_info_tool(context, StructuredTool),
        _build_transfer_tool(context, StructuredTool),
        _build_search_knowledge_tool(context, StructuredTool),
    ]


def build_customer_openai_tool_definitions() -> list[dict]:
    """构造 OpenAI tool schema，避免维护第二份 function_defs。"""
    return [
        _openai_tool_schema(
            "get_order_info",
            ORDER_INFO_DESCRIPTION,
            OrderInfoArgs,
        ),
        _openai_tool_schema(
            "get_product_info",
            PRODUCT_INFO_DESCRIPTION,
            ProductInfoArgs,
        ),
        _openai_tool_schema(
            "get_logistics_info",
            LOGISTICS_INFO_DESCRIPTION,
            LogisticsInfoArgs,
        ),
        _openai_tool_schema(
            "transfer_to_human",
            TRANSFER_TO_HUMAN_DESCRIPTION,
            TransferToHumanArgs,
        ),
        _openai_tool_schema(
            "search_knowledge",
            SEARCH_KNOWLEDGE_DESCRIPTION,
            SearchKnowledgeArgs,
        ),
    ]


def _openai_tool_schema(
    name: str,
    description: str,
    args_schema: type[BaseModel],
) -> dict:
    parameters = args_schema.model_json_schema()
    parameters.pop("title", None)
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


def _service_unavailable(message: str) -> str:
    return json.dumps({"message": message}, ensure_ascii=False)


def resolve_customer_order_identity(
    session: Session | None,
) -> CustomerOrderIdentity | None:
    """从可信会话字段解析客户订单身份。"""
    if session is None:
        return None
    user_id = (session.user_id or "").strip()
    if not user_id:
        return None
    extra_info = _load_session_extra_info(session.extra_info)
    outer_user_id = _normalize_identity(extra_info.get("outer_user_id"))
    if session.channel == Channel.YOUZAN.value:
        return CustomerOrderIdentity(
            buyer_id=user_id,
            outer_user_id=outer_user_id or None,
        )
    if outer_user_id:
        return CustomerOrderIdentity(outer_user_id=outer_user_id)
    return None


def _build_order_info_tool(context: CustomerToolContext, structured_tool: Any) -> Any:
    async def get_order_info_tool(order_no: str) -> str:
        identity = resolve_customer_order_identity(context.session)
        if identity is None:
            return _ownership_denied(order_no)
        if context.knowledge_retriever is None:
            return _service_unavailable("订单查询服务暂不可用")
        from app.service.llm.function_tool_order import get_order_info

        return await get_order_info(
            context.knowledge_retriever,
            youzan_client=context.youzan_client,
            order_no=order_no,
            order_repo=context.order_repo,
            config_repo=context.config_repo,
            buyer_id=identity.buyer_id,
            outer_user_id=identity.outer_user_id,
        )

    return structured_tool.from_function(
        coroutine=get_order_info_tool,
        name="get_order_info",
        description=ORDER_INFO_DESCRIPTION,
        args_schema=OrderInfoArgs,
    )


def _build_product_info_tool(context: CustomerToolContext, structured_tool: Any) -> Any:
    async def get_product_info_tool(
        product_name: str = "",
        product_id: str = "",
    ) -> str:
        if context.knowledge_retriever is None:
            return _service_unavailable("商品查询服务暂不可用")
        from app.service.llm.function_tool_product import get_product_info

        return await get_product_info(
            context.knowledge_retriever,
            context.session,
            youzan_client=context.youzan_client,
            product_name=product_name,
            product_id=product_id,
            product_repo=context.product_repo,
            knowledge_product_repo=context.knowledge_product_repo,
            analytics_repo=context.analytics_repo,
            history_repo=context.history_repo,
            embedding_searcher=context.embedding_searcher,
        )

    return structured_tool.from_function(
        coroutine=get_product_info_tool,
        name="get_product_info",
        description=PRODUCT_INFO_DESCRIPTION,
        args_schema=ProductInfoArgs,
    )


def _build_logistics_info_tool(
    context: CustomerToolContext,
    structured_tool: Any,
) -> Any:
    async def get_logistics_info_tool(order_no: str) -> str:
        identity = resolve_customer_order_identity(context.session)
        if identity is None:
            return _ownership_denied(order_no)
        if context.knowledge_retriever is None:
            return _service_unavailable("物流查询服务暂不可用")
        from app.service.llm.function_tool_order import get_logistics_info

        return await get_logistics_info(
            context.knowledge_retriever,
            youzan_client=context.youzan_client,
            order_no=order_no,
            order_repo=context.order_repo,
            config_repo=context.config_repo,
            buyer_id=identity.buyer_id,
            outer_user_id=identity.outer_user_id,
        )

    return structured_tool.from_function(
        coroutine=get_logistics_info_tool,
        name="get_logistics_info",
        description=LOGISTICS_INFO_DESCRIPTION,
        args_schema=LogisticsInfoArgs,
    )


def _build_transfer_tool(context: CustomerToolContext, structured_tool: Any) -> Any:
    async def transfer_to_human_tool(reason: str) -> str:
        if context.transfer_handler is not None:
            return await context.transfer_handler(reason)

        return json.dumps(
            {"status": "pending", "message": "正在为您转接人工客服"},
            ensure_ascii=False,
        )

    return structured_tool.from_function(
        coroutine=transfer_to_human_tool,
        name="transfer_to_human",
        description=TRANSFER_TO_HUMAN_DESCRIPTION,
        args_schema=TransferToHumanArgs,
        return_direct=True,
    )


def _build_search_knowledge_tool(
    context: CustomerToolContext,
    structured_tool: Any,
) -> Any:
    async def search_knowledge_tool(query: str) -> str:
        if context.knowledge_retriever is None:
            return _service_unavailable("知识库服务暂不可用")
        from app.service.llm.function_tool_product import search_knowledge

        return await search_knowledge(context.knowledge_retriever, query=query)

    return structured_tool.from_function(
        coroutine=search_knowledge_tool,
        name="search_knowledge",
        description=SEARCH_KNOWLEDGE_DESCRIPTION,
        args_schema=SearchKnowledgeArgs,
    )


def _ownership_denied(order_no: str) -> str:
    return json.dumps(
        {
            "order_no": order_no,
            "available": False,
            "message": ORDER_OWNERSHIP_DENIAL_MESSAGE,
        },
        ensure_ascii=False,
    )


def _load_session_extra_info(extra_info: str) -> dict[str, Any]:
    try:
        payload = json.loads(extra_info or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_identity(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
