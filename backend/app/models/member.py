"""会员储值/积分/优惠券账务域数据模型。"""

from dataclasses import dataclass


class MemberEventType:
    """有赞会员域 Webhook 事件类型（小写归一化）。"""

    CUSTOMER = "scrm_customer_event"
    POINTS = "points"
    COUPON = "coupon_customer_promotion"
    CARD = "scrm_customer_card"


class LedgerSource:
    """账务数据来源。"""

    WEBHOOK = "webhook"
    IMPORT = "import"
    ORDER = "order"
    LOCAL = "local"


class CouponStatus:
    """优惠券生命周期状态（有赞推送值）。"""

    TAKE = "TAKE"
    CONSUME = "CONSUME"
    BACK = "BACK"


@dataclass
class MemberBalanceState:
    """会员余额与卡片状态快照（按 mobile 唯一）。"""

    customer_id: str = ""
    mobile: str = ""
    yz_open_id: str = ""
    display_name: str = ""
    is_member: int = 0
    card_alias: str = ""
    card_no: str = ""
    card_status: str = ""
    points: int = 0
    stored_value_fen: int = 0


@dataclass
class PointsLedgerEntry:
    """一条积分变动流水。"""

    unique_id: str
    amount: int
    total: int
    event_type: str
    source: str = LedgerSource.WEBHOOK
    biz_type: str = ""
    biz_id: str = ""
    customer_id: str = ""
    mobile: str = ""
    yz_open_id: str = ""
    occurred_at: str = ""


@dataclass
class CouponInventoryEntry:
    """一条优惠券生命周期记录。"""

    coupon_id: str
    status: str
    mobile: str
    coupon_group_id: str = ""
    customer_id: str = ""
    order_no: str = ""
    title: str = ""
    value_fen: int = 0
    detail_json: str = "{}"
    source: str = LedgerSource.WEBHOOK
    occurred_at: str = ""
    template_id: str = ""
    valid_from: str = ""
    valid_until: str = ""
    deducted_fen: int = 0
    consumed_at: str = ""
    refunded_at: str = ""
