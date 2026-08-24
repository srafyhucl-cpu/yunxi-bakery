"""企微员工助手商品销量排行展示格式。"""

from __future__ import annotations

from typing import Any

from app.models.employee_agent import ToolResult


def build_top_products_tool_result(
    query: str,
    rows: list[dict[str, Any]],
) -> ToolResult:
    """构造商品销量排行结果。"""
    if not rows:
        return ToolResult(ok=True, summary=f"{query}：没有查到匹配商品订单。")
    lines = [f"{query}：按销量粗略排行如下："]
    for index, row in enumerate(rows, 1):
        amount_yuan = int(row.get("total_amount_fen", 0) or 0) / 100
        lines.append(
            f"{index}. {row.get('product_titles') or '未记录商品'}："
            f"{int(row.get('total_quantity', 0) or 0)} 件，"
            f"{int(row.get('order_count', 0) or 0)} 单，{amount_yuan:.2f} 元"
        )
    tie_caution = _top_products_tie_caution(rows)
    if tie_caution:
        lines.append(tie_caution)
    return ToolResult(
        ok=True,
        summary="\n".join(lines),
        items=rows,
        next_action=_top_products_next_action(tie_caution),
    )


def _top_products_tie_caution(rows: list[dict[str, Any]]) -> str:
    if len(rows) < 2:
        return ""
    top_quantity = int(rows[0].get("total_quantity", 0) or 0)
    second_quantity = int(rows[1].get("total_quantity", 0) or 0)
    if top_quantity != second_quantity:
        return ""
    if top_quantity <= 1:
        return "提示：当前销量并列且样本很少，还不能判断单一爆款。"
    return "提示：当前第一梯队销量并列，请结合金额、库存和后续订单再判断主推商品。"


def _top_products_next_action(tie_caution: str) -> str:
    if tie_caution:
        return "如需备货判断，建议继续结合库存、履约压力和后续订单趋势。"
    return "如需备货判断，建议继续结合库存和履约压力。"
