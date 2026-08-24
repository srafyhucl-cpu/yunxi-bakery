"""订单支付状态与纯函数辅助逻辑。"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.order import Order

PAYMENT_STATUS_UNPAID = "unpaid"
PAYMENT_STATUS_PAID = "paid"
PAYMENT_STATUS_EXPIRED = "expired"
PAYMENT_STATUS_PARTIAL = "partial"
PAYMENT_METHOD_MOCK = "mock"
PAYMENT_METHOD_WECHAT = "wechat"
PAYMENT_METHOD_BALANCE = "balance"
PAYMENT_METHOD_COMBINED = "combined"
PAYMENT_MODE_MOCK = "mock"
PAYMENT_MODE_WECHAT = "wechat"
PAYMENT_TIMEOUT_MINUTES = 30
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class PaymentSession:
    """统一支付会话返回结构。"""

    mode: str
    order_id: str
    payment_method: str
    payment_status: str
    payload: dict


def build_initial_payment(now_text: str) -> dict:
    """构建订单初始支付状态。"""
    return {
        "status": PAYMENT_STATUS_UNPAID,
        "method": "",
        "paidAt": "",
        "expiredAt": "",
        "expiredReason": "",
        "createdAt": now_text,
    }


def build_balance_payment(now_text_value: str, balance_fen: int) -> dict:
    """构建全额储值余额支付状态。"""
    return {
        "status": PAYMENT_STATUS_PAID,
        "method": PAYMENT_METHOD_BALANCE,
        "balanceFen": balance_fen,
        "paidAt": now_text_value,
        "expiredAt": "",
        "expiredReason": "",
        "createdAt": now_text_value,
    }


def build_combined_payment(
    now_text_value: str, balance_fen: int, remain_fen: int
) -> dict:
    """构建组合支付中间状态（余额部分已扣，差额待付）。"""
    return {
        "status": PAYMENT_STATUS_PARTIAL,
        "method": PAYMENT_METHOD_COMBINED,
        "balanceFen": balance_fen,
        "remainFen": remain_fen,
        "paidAt": "",
        "expiredAt": "",
        "expiredReason": "",
        "createdAt": now_text_value,
    }


def build_points_payment(
    now_text_value: str,
    *,
    balance_fen: int,
    points_fen: int,
    points_used: int,
    remain_fen: int,
) -> dict:
    """构建含积分抵扣的组合支付中间状态。"""
    payment = build_combined_payment(now_text_value, balance_fen, remain_fen)
    payment.update(
        {
            "pointsFen": points_fen,
            "pointsUsed": points_used,
        }
    )
    return payment


def build_mock_payment_session(order_id: str) -> PaymentSession:
    """构建 mock 支付会话，供开发和无商户配置环境使用。"""
    return PaymentSession(
        mode=PAYMENT_MODE_MOCK,
        order_id=order_id,
        payment_method=PAYMENT_METHOD_MOCK,
        payment_status=PAYMENT_STATUS_UNPAID,
        payload={
            "action": "mock-pay",
            "message": "当前环境未启用微信支付，使用模拟支付兜底",
        },
    )


def loads_payment(raw: str) -> dict:
    """解析订单支付 JSON。"""
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return build_initial_payment("")
    return value if isinstance(value, dict) else build_initial_payment("")


def compute_remain_fen(
    total_fen: int, coupon_fen: int, balance_fen: int, points_fen: int
) -> int:
    """唯一剩余应付公式：total - coupon - balance - points（不小于 0）。"""
    return max(
        0,
        int(total_fen or 0)
        - int(coupon_fen or 0)
        - int(balance_fen or 0)
        - int(points_fen or 0),
    )


def payment_status_value(order: Order) -> str:
    """读取订单支付状态字符串。"""
    payment = loads_payment(order.payment)
    return str(payment.get("status", PAYMENT_STATUS_UNPAID))


def dumps_payment(payment: dict) -> str:
    """序列化订单支付 JSON。"""
    return json.dumps(payment, ensure_ascii=False)


def loads_json_object(raw: str) -> dict:
    """解析 JSON 对象文本。"""
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("微信支付通知 JSON 无效") from exc
    if not isinstance(value, dict):
        raise ValueError("微信支付通知 JSON 无效")
    return value


def parse_time(value: str) -> datetime | None:
    """解析标准订单时间。"""
    try:
        return datetime.strptime(value, TIME_FORMAT)
    except ValueError:
        return None


def now_text() -> str:
    """返回当前标准时间文本。"""
    return datetime.now().strftime(TIME_FORMAT)


def status_value(order: Order) -> str:
    """读取订单状态字符串值。"""
    return order.status.value if hasattr(order.status, "value") else str(order.status)


def loads_products(raw: str) -> list[dict[str, Any]]:
    """解析订单商品列表。"""
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def build_order_description(order: Order) -> str:
    """构建微信支付订单标题。"""
    products = loads_products(order.products)
    first_item = products[0] if products else {}
    title = str(first_item.get("title", "")).strip()
    return title[:127] or "芸熙烘焙订单"


def extract_openid(user_id: str) -> str:
    """从前台用户标识中提取微信 openid。"""
    value = str(user_id or "").strip()
    if value.startswith("wx_"):
        return value[3:]
    if value.startswith("openid_"):
        return value
    return ""


__all__ = [
    "PAYMENT_METHOD_MOCK",
    "PAYMENT_METHOD_WECHAT",
    "PAYMENT_MODE_MOCK",
    "PAYMENT_MODE_WECHAT",
    "PAYMENT_STATUS_EXPIRED",
    "PAYMENT_STATUS_PAID",
    "PAYMENT_STATUS_PARTIAL",
    "PAYMENT_STATUS_UNPAID",
    "PAYMENT_TIMEOUT_MINUTES",
    "PaymentSession",
    "TIME_FORMAT",
    "build_balance_payment",
    "build_combined_payment",
    "build_initial_payment",
    "build_mock_payment_session",
    "build_order_description",
    "build_points_payment",
    "compute_remain_fen",
    "dumps_payment",
    "extract_openid",
    "loads_json_object",
    "loads_payment",
    "now_text",
    "payment_status_value",
    "parse_time",
    "status_value",
]
