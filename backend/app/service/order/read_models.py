"""订单读模型与看板筛选辅助函数。"""

from app.models.order import OrderStatus
from app.utils import yuan_to_fen

ADMIN_ORDER_BOARD_FILTERS = [
    {
        "key": "all",
        "label": "全部订单",
        "description": "当前筛选范围",
    },
    {
        "key": "unpaid",
        "label": "待支付",
        "description": "需要跟进付款",
    },
    {
        "key": "pending",
        "label": "待确认",
        "description": "新订单待接单",
    },
    {
        "key": "fulfilling",
        "label": "履约中",
        "description": "确认/制作/配送",
    },
    {
        "key": "done",
        "label": "已完成",
        "description": "已交付订单",
    },
    {
        "key": "closed",
        "label": "已关闭",
        "description": "取消或支付超时",
    },
]
ADMIN_ORDER_FULFILLING_STATUSES = {
    OrderStatus.CONFIRMED.value,
    OrderStatus.MAKING.value,
    OrderStatus.DELIVERING.value,
}


def normalize_board_filter(board_filter: str) -> str:
    """规范化后台看板筛选键。"""
    value = str(board_filter or "").strip()
    allowed = {item["key"] for item in ADMIN_ORDER_BOARD_FILTERS}
    return value if value in allowed and value != "all" else ""


def summarize_board_row(board_filter: str, rows: list[dict]) -> tuple[int, int]:
    """汇总单个看板卡片的订单数与金额。"""
    matched_rows = [row for row in rows if summary_row_matches(board_filter, row)]
    count = sum(int(row.get("order_count", 0) or 0) for row in matched_rows)
    amount_fen = sum(
        yuan_to_fen(row.get("total_amount", 0) or 0) for row in matched_rows
    )
    return count, amount_fen


def summary_row_matches(board_filter: str, row: dict) -> bool:
    """判断汇总行是否命中指定看板筛选。"""
    status = str(row.get("status", ""))
    payment_status = str(row.get("payment_status", "unpaid") or "unpaid")
    if board_filter == "all":
        return True
    if board_filter == "unpaid":
        return payment_status == "unpaid" and status != OrderStatus.CANCELLED.value
    if board_filter == "pending":
        return status == OrderStatus.PENDING.value
    if board_filter == "fulfilling":
        return status in ADMIN_ORDER_FULFILLING_STATUSES
    if board_filter == "done":
        return status == OrderStatus.DONE.value
    if board_filter == "closed":
        return status == OrderStatus.CANCELLED.value or payment_status == "expired"
    return False


__all__ = [
    "ADMIN_ORDER_BOARD_FILTERS",
    "ADMIN_ORDER_FULFILLING_STATUSES",
    "normalize_board_filter",
    "summarize_board_row",
    "summary_row_matches",
]
