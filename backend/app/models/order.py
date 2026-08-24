from dataclasses import dataclass, field
from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    MAKING = "making"
    DELIVERING = "delivering"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass
class Order:
    id: str
    session_id: str
    channel: str
    user_id: str
    products: str  # JSON
    total_amount: float = 0.0
    delivery: str = "{}"  # JSON
    payment: str = "{}"  # JSON
    status: OrderStatus = OrderStatus.PENDING
    remark: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class OrderEvent:
    """小程序订单状态事件，用于用户侧进度时间线。"""

    order_id: str
    status: str
    operator: str
    note: str
    created_at: str
    id: int = 0


@dataclass
class YouzanOrderData:
    """有赞交易订单 Upsert 数据容器，封装 youzan_orders 全量可写字段。"""

    order_no: str
    buyer_id: str
    status: str
    amount_fen: int
    product_titles: str
    total_quantity: int
    created_at: str
    updated_at: str
    logistics_no: str = ""
    logistics_status: str = ""
    pay_time: str = ""
    consign_time: str = ""
    pay_type_str: str = ""
    express_type: int = 0
    refund_state: int = 0
    post_fee_fen: int = 0
    discount_fen: int = 0
    delivery_province: str = ""
    delivery_city: str = ""
    delivery_district: str = ""
    delivery_time: str = ""
    outer_user_id: str = ""
    order_items_json: str = field(default="[]")
