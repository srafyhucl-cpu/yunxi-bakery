"""优惠券模块数据模型。"""

from dataclasses import dataclass


class CouponType:
    """券类型枚举。"""

    FULL_REDUCTION = "FULL_REDUCTION"
    NO_THRESHOLD = "NO_THRESHOLD"
    DISCOUNT = "DISCOUNT"


class CouponTemplateStatus:
    """券模板状态。"""

    ACTIVE = "active"
    DISABLED = "disabled"


class CouponGrantStatus:
    """发券记录状态。"""

    GRANTED = "granted"
    REVOKED = "revoked"


@dataclass
class CouponTemplate:
    """券模板（有赞同步或 local 后台创建）。"""

    id: str
    name: str
    coupon_type: str
    threshold_fen: int = 0
    value_fen: int = 0
    discount_bp: int = 0
    cap_fen: int = 0
    valid_from: str = ""
    valid_until: str = ""
    scope_json: str = "{}"
    status: str = CouponTemplateStatus.ACTIVE
    source: str = "youzan"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CouponGrant:
    """发券记录（local 模式后台发券）。"""

    id: str
    template_id: str
    mobile: str
    coupon_code: str
    customer_id: str = ""
    granted_by: str = "admin"
    channel: str = "admin"
    audience_json: str = "{}"
    status: str = CouponGrantStatus.GRANTED
    created_at: str = ""
