"""企微员工助手配送时间展示格式。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.utils import BEIJING_TIMEZONE, now_beijing_naive

DELIVERY_OVERDUE_MARKER = "已过约送时间"


def employee_delivery_time_text(order: dict[str, Any]) -> str:
    """格式化员工可读配送时间。"""
    delivery_time = str(order.get("delivery_time") or "").strip()
    if not delivery_time:
        return "未约送"
    overdue_text = (
        f"（{DELIVERY_OVERDUE_MARKER}）"
        if _is_delivery_time_overdue(delivery_time)
        else ""
    )
    return f"约送 {delivery_time}{overdue_text}"


def _is_delivery_time_overdue(delivery_time: str) -> bool:
    normalized_delivery_time = delivery_time.strip()
    if not normalized_delivery_time:
        return False
    try:
        parsed_delivery_time = datetime.fromisoformat(normalized_delivery_time)
    except ValueError:
        return False
    if parsed_delivery_time.tzinfo is not None:
        parsed_delivery_time = parsed_delivery_time.astimezone(
            BEIJING_TIMEZONE
        ).replace(tzinfo=None)
    return parsed_delivery_time < now_beijing_naive()
