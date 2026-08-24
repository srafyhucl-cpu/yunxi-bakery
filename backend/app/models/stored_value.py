"""会员储值余额域数据模型。"""

from dataclasses import dataclass


class RechargeStatus:
    """充值单生命周期状态。"""

    UNPAID = "unpaid"
    PAID = "paid"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class BalanceBizType:
    """储值流水业务类型。"""

    RECHARGE = "recharge"
    ORDER_PAY = "order_pay"
    ORDER_REFUND = "order_refund"


class BalanceSource:
    """储值流水来源。"""

    RECHARGE = "recharge"
    ORDER = "order"
    WEBHOOK = "webhook"
    IMPORT = "import"


@dataclass
class RechargeOrder:
    """一条充值单记录。"""

    id: str
    user_id: str
    mobile: str
    amount_fen: int = 0
    status: str = RechargeStatus.UNPAID
    payment_method: str = ""
    paid_at: str = ""
    expired_at: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class BalanceLedgerEntry:
    """一条储值余额变动流水（amount_fen 带符号）。"""

    unique_id: str
    user_id: str = ""
    mobile: str = ""
    customer_id: str = ""
    amount_fen: int = 0
    balance_after_fen: int = 0
    biz_type: str = BalanceBizType.RECHARGE
    biz_id: str = ""
    source: str = BalanceSource.RECHARGE
    occurred_at: str = ""
