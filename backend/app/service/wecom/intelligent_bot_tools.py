"""企微智能机器人只读业务工具服务。"""

from typing import Any

from app.logger import setup_logger
from app.service.wecom.intelligent_bot_knowledge_format import knowledge_answer_text
from app.service.wecom.intelligent_bot_plugin import extract_text
from app.service.wecom.intelligent_bot_product_action import product_next_action
from app.service.wecom.intelligent_bot_tool_format import (
    compact_knowledge_entry,
    compact_order,
    filter_products,
    is_featured_query,
    order_line,
    product_line,
)
from app.service.wecom.intelligent_bot_tool_response import (
    extract_limit,
    failed,
    missing_query,
    ok_response,
    unavailable,
)

logger = setup_logger()


class WeComBotBusinessToolService:
    """把现有业务服务包装成企微可配置的只读工具。"""

    def __init__(
        self,
        *,
        order_service: Any = None,
        order_lookup_service: Any = None,
        catalog_service: Any = None,
        knowledge_retriever: Any = None,
    ) -> None:
        self._order_service = order_service
        self._order_lookup_service = order_lookup_service
        self._catalog_service = catalog_service
        self._knowledge_retriever = knowledge_retriever

    async def lookup_orders(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = extract_text(payload)
        limit = extract_limit(payload)
        if not query:
            return missing_query(
                "order_lookup", "请提供订单号、手机号、客户名或商品关键词。"
            )
        if self._order_lookup_service is not None:
            try:
                return await self._order_lookup_service.lookup_orders(query, limit)
            except Exception as exc:
                logger.error("企微订单查询编排失败 query=%s err=%s", query, exc)
                return failed("order_lookup", "订单查询失败，请稍后重试或到后台查看。")
        if self._order_service is None:
            return unavailable("order_lookup", "订单查询")
        try:
            result = await self._order_service.list_admin_orders(
                page=1,
                keyword=query,
            )
        except Exception as exc:
            logger.error("企微订单查询工具失败 query=%s err=%s", query, exc)
            return failed("order_lookup", "订单查询失败，请稍后重试或到后台查看。")
        orders = [compact_order(item) for item in result.get("items", [])[:limit]]
        total = int(result.get("total", len(orders)) or 0)
        orders_text = "\n".join(order_line(item) for item in orders) or "未找到匹配订单"
        return ok_response(
            "order_lookup",
            query,
            f"找到 {total} 个匹配订单，当前返回 {len(orders)} 个。",
            ordersText=orders_text,
            orders=orders,
            nextAction="如需改状态或处理退款，请进入后台订单页操作。",
        )

    async def lookup_products(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = extract_text(payload)
        limit = extract_limit(payload)
        if self._catalog_service is None:
            return unavailable("product_lookup", "商品库存查询")
        if not query:
            return missing_query("product_lookup", "请提供商品名、品类或库存问题。")
        try:
            products = await self._catalog_service.list_products(
                featured=is_featured_query(query)
            )
        except Exception as exc:
            logger.error("企微商品查询工具失败 query=%s err=%s", query, exc)
            return failed("product_lookup", "商品查询失败，请稍后重试或到后台查看。")
        matched_products = filter_products(products, query)[:limit]
        products_text = (
            "\n".join(product_line(item) for item in matched_products)
            or "未找到匹配商品"
        )
        return ok_response(
            "product_lookup",
            query,
            f"找到 {len(matched_products)} 个可展示商品。",
            productsText=products_text,
            products=matched_products,
            nextAction=product_next_action(query, matched_products),
        )

    async def answer_knowledge(self, payload: dict[str, Any]) -> dict[str, Any]:
        question = extract_text(payload)
        limit = extract_limit(payload)
        if self._knowledge_retriever is None:
            return unavailable("knowledge_answer", "知识库问答")
        if not question:
            return missing_query("knowledge_answer", "请提供要查询的规则、话术或问题。")
        try:
            if hasattr(self._knowledge_retriever, "search_keyword_only"):
                entries = await self._knowledge_retriever.search_keyword_only(
                    question, limit=limit
                )
            else:
                entries = await self._knowledge_retriever.search(question, limit=limit)
        except Exception as exc:
            logger.error("企微知识库工具失败 question=%s err=%s", question, exc)
            return failed(
                "knowledge_answer", "知识库查询失败，请稍后重试或到后台查看。"
            )
        sources = [compact_knowledge_entry(entry) for entry in entries[:limit]]
        answer = knowledge_answer_text(question, sources)
        return ok_response(
            "knowledge_answer",
            question,
            f"找到 {len(sources)} 条相关知识。",
            answer=answer,
            sourcesText=answer,
            sources=sources,
            nextAction="员工可复制建议回复；如知识缺失，请到后台知识库补充。",
        )
