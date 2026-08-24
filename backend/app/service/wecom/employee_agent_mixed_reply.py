"""企微员工助手多工具回复整理。"""

from __future__ import annotations

import re

from app.models.employee_agent import AgentIntent, AgentPlan, ToolResult

KNOWLEDGE_MISS_TEXT = "未找到匹配知识。"
LOW_STOCK_THRESHOLD = 5
NO_STOCK_VALUE = 0
STOCK_PATTERN = re.compile(r"库存\s*(\d+)")
CUSTOMER_REPLY_KEYWORDS = ("怎么跟客户说", "怎么回复客户", "回复客户", "话术")


def build_mixed_tool_reply(
    query: str,
    plan: AgentPlan,
    tool_results: list[ToolResult],
) -> str | None:
    """为组合工具结果生成更像员工助手的确定性回复。"""
    if plan.intent != AgentIntent.MULTI_TOOL:
        return None
    if plan.tools == ("order_dynamic_query", "knowledge_answer"):
        return _build_order_customer_reply(query, tool_results)
    if plan.tools != ("product_lookup", "knowledge_answer"):
        return None
    if len(tool_results) < 2:
        return None
    product_result, knowledge_result = tool_results[0], tool_results[1]
    if not _is_knowledge_miss(knowledge_result) or not product_result.summary.strip():
        return None
    return "\n".join(
        [
            product_result.summary,
            _product_stock_action_reply(query, product_result),
            _next_action_line(product_result),
        ]
    )


def _build_order_customer_reply(
    query: str,
    tool_results: list[ToolResult],
) -> str | None:
    if len(tool_results) < 2 or not _needs_customer_reply(query):
        return None
    order_result, knowledge_result = tool_results[0], tool_results[1]
    if not order_result.summary.strip():
        return None
    lines = [order_result.summary, _order_customer_reply_text(query, order_result)]
    if not _is_knowledge_miss(knowledge_result) and knowledge_result.summary.strip():
        lines.append("知识库参考：" + knowledge_result.summary.strip())
    lines.append(_order_next_action_line(query, order_result))
    return "\n".join(lines)


def _needs_customer_reply(query: str) -> bool:
    return any(keyword in query for keyword in CUSTOMER_REPLY_KEYWORDS)


def _order_customer_reply_text(query: str, result: ToolResult) -> str:
    if "退款" in query or "售后" in query:
        if _looks_empty_order_result(result):
            return (
                "给客户可复制回复：亲，当前没有查到这笔需求对应的退款/售后记录。"
                "我先帮您继续核对订单状态，如有最新处理进度会及时同步。"
            )
        return (
            "给客户可复制回复：亲，您的退款/售后需求我们已经收到，"
            "正在按订单记录核对处理进度。请您稍等，我们确认后会尽快同步结果。"
        )
    if _looks_empty_order_result(result):
        return (
            "给客户可复制回复：亲，当前没有查到需要发货处理的订单记录。"
            "我先帮您再核对一下订单状态，如有更新会及时告知。"
        )
    return (
        "给客户可复制回复：亲，您的订单目前还在备货处理中，"
        "我们会按约定时间尽快安排发货/配送；如状态更新，会第一时间同步给您。"
    )


def _looks_empty_order_result(result: ToolResult) -> bool:
    summary = result.summary
    return (
        "没有查到" in summary
        or "无退款订单" in summary
        or "0 单" in summary
        or "0单" in summary
    )


def _order_next_action_line(query: str, result: ToolResult) -> str:
    if result.next_action.strip():
        return "下一步：" + result.next_action.strip()
    if "退款" in query or "售后" in query:
        return "下一步：先核对订单尾号和售后状态，再把处理进度同步给客户。"
    return "下一步：先按订单尾号核对发货/配送状态，再复制话术回复客户。"


def _is_knowledge_miss(result: ToolResult) -> bool:
    return result.summary.strip() == KNOWLEDGE_MISS_TEXT


def _product_stock_action_reply(query: str, result: ToolResult) -> str:
    stock_values = _extract_stock_values(result)
    if stock_values and max(stock_values) <= NO_STOCK_VALUE:
        return (
            "员工建议：系统显示当前没有可售库存，先不要承诺有货；优先向客户推荐同品类、"
            "相近价位或同场景替代款，并同步确认配送/自提时间。"
        )
    if stock_values and min(stock_values) <= LOW_STOCK_THRESHOLD:
        return (
            "员工建议：当前库存偏低，先确认客户需要的数量、规格和配送/自提时间；"
            "如需求超过库存，再推荐同品类、相近价位或同场景替代款。"
        )
    if "没货" in query or "库存不够" in query:
        return (
            "员工建议：实时商品数据看还有库存，先不要直接说没货；请确认客户需要的数量、"
            "规格和配送/自提时间，如实际需求超过库存，再推荐相近口味、同品类或同价位替代款。"
        )
    return (
        "员工建议：先按实时库存回复客户，并确认客户需要的数量、规格和配送/自提时间；"
        "如当前款式不合适，再推荐相近口味、同品类或同价位替代款。"
    )


def _extract_stock_values(result: ToolResult) -> list[int]:
    values: list[int] = []
    for item in result.items:
        stock = item.get("stock")
        if isinstance(stock, int):
            values.append(stock)
    values.extend(int(value) for value in STOCK_PATTERN.findall(result.summary))
    return values


def _next_action_line(result: ToolResult) -> str:
    if result.next_action.strip():
        return "下一步：" + result.next_action.strip()
    return "下一步：员工回复前再到小程序或后台核对实时库存，避免超卖。"
