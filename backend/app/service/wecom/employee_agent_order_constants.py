"""企微员工助手订单规划常量。"""

from __future__ import annotations

import re

DEFAULT_RESULT_LIMIT = 5
MAX_RESULT_LIMIT = 10
CHINESE_DAY_NUMBERS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
ORDER_NO_PATTERN = re.compile(r"\bE\d{12,}\b", re.IGNORECASE)
ORDER_PENDING_STATUSES = ("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_CONFIRM_GOODS")
ORDER_EFFECTIVE_STATUSES = (
    "WAIT_SELLER_SEND_GOODS",
    "WAIT_BUYER_CONFIRM_GOODS",
    "TRADE_SUCCESS",
)
ORDER_STATUS_KEYWORDS = {
    "WAIT_SELLER_SEND_GOODS": (
        "待发货",
        "没发货",
        "未发货",
        "还没发",
        "发货",
        "没处理",
    ),
    "WAIT_BUYER_CONFIRM_GOODS": ("待收货", "已发货", "配送中"),
    "TRADE_SUCCESS": ("已完成", "交易成功", "完成"),
    "TRADE_CLOSED": ("已关闭", "关闭", "取消"),
    "WAIT_BUYER_PAY": ("待付款", "未付款"),
}
ORDER_QUERY_PUNCTUATION_PATTERN = re.compile(r"[，。？！、；：,.?!;:]")
