"""配送领域的内部契约模型。"""

from dataclasses import dataclass
from enum import Enum


class FulfillmentMethod(str, Enum):
    """首发支持的履约方式。"""

    PICKUP = "pickup"
    BEIJING_DELIVERY = "beijing_delivery"


class DeliveryQuoteStatus(str, Enum):
    """配送报价生命周期状态。"""

    QUOTING = "quoting"
    QUOTED = "quoted"
    EXPIRED = "expired"
    ADDRESS_OUT_OF_RANGE = "address_out_of_range"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PENDING_CONFIRMATION = "pending_confirmation"


class DeliveryOrderStatus(str, Enum):
    """配送单生命周期状态。"""

    NOT_APPLICABLE = "not_applicable"
    PENDING_CREATE = "pending_create"
    CREATED = "created"
    ACCEPTED = "accepted"
    PICKING_UP = "picking_up"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class DeliveryQuote:
    """配送报价快照，金额统一使用整数分。"""

    quote_id: str
    user_id: str
    fulfillment_method: FulfillmentMethod
    request_hash: str
    goods_total_fen: int
    delivery_fee_fen: int | None
    quote_total_fen: int | None
    status: DeliveryQuoteStatus
    expires_at: str
    provider: str = ""
    message: str = ""


@dataclass(frozen=True)
class DeliveryOrder:
    """外部配送单的本地快照。"""

    order_id: str
    provider: str
    provider_order_id: str
    status: DeliveryOrderStatus
    delivery_fee_fen: int | None
    pickup_address: str
    receiver_address: str
    last_synced_at: str


def build_payable_fen(
    goods_total_fen: int,
    delivery_fee_fen: int,
    discount_fen: int = 0,
    coupon_deduction_fen: int = 0,
    points_deduction_fen: int = 0,
    balance_deduction_fen: int = 0,
) -> int:
    """按金额快照计算应付金额，不允许结果小于零。"""
    values = (
        goods_total_fen,
        delivery_fee_fen,
        discount_fen,
        coupon_deduction_fen,
        points_deduction_fen,
        balance_deduction_fen,
    )
    if any(value < 0 for value in values):
        raise ValueError("金额不能为负数")
    return max(
        0,
        goods_total_fen
        + delivery_fee_fen
        - discount_fen
        - coupon_deduction_fen
        - points_deduction_fen
        - balance_deduction_fen,
    )


def can_pay_quote(status: DeliveryQuoteStatus, delivery_fee_fen: int | None) -> bool:
    """判断报价是否具备支付条件。"""
    return status is DeliveryQuoteStatus.QUOTED and delivery_fee_fen is not None
