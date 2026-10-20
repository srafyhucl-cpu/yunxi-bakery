"""优惠券业务规则纯函数（无 IO，可独立单测）。"""

from app.models.coupon import CouponTemplateStatus, CouponType

FULL_DISCOUNT_BP = 10_000
MIN_DISCOUNT_FEN = 1


def is_coupon_available(template: dict, total_fen: int, now_text: str) -> bool:
    """判断模板券在当前订单金额与时间下是否可用。"""
    if (
        str(template.get("status", CouponTemplateStatus.ACTIVE))
        != CouponTemplateStatus.ACTIVE
    ):
        return False
    if (
        int(template.get("value_fen", 0) or 0) <= 0
        and int(template.get("discount_bp", 0) or 0) <= 0
    ):
        return False
    total = max(0, int(total_fen or 0))
    if total <= 0:
        return False
    today = str(now_text or "")[:10]
    valid_from = str(template.get("valid_from", "") or "")[:10]
    valid_until = str(template.get("valid_until", "") or "")[:10]
    if valid_from and today < valid_from:
        return False
    if valid_until and today > valid_until:
        return False
    coupon_type = str(template.get("coupon_type", ""))
    if coupon_type == CouponType.FULL_REDUCTION:
        threshold = int(template.get("threshold_fen", 0) or 0)
        if total < threshold:
            return False
    return True


def apply_row_validity(template: dict, row: dict) -> dict:
    """把券自身的有效期覆盖到模板上（券级有效期比模板更严格）。

    有赞「领券后 N 天有效」型券模板的有效期描述的是**活动**有效期
    （2026-10-20 生产实测：2024-09-26 ~ 2100-01-01），只看模板会让已过期
    券继续可用（资损）。券自身带有效期时必须以券为准；券没有有效期时
    保留模板口径，不做推断。
    """
    valid_from = str(row.get("valid_from", "") or "")
    valid_until = str(row.get("valid_until", "") or "")
    if valid_from:
        template["valid_from"] = valid_from
    if valid_until:
        template["valid_until"] = valid_until
    return template


def calc_discount(template: dict, total_fen: int) -> int:
    """计算券可抵扣金额（分），不超过订单应付。"""
    total = max(0, int(total_fen or 0))
    coupon_type = str(template.get("coupon_type", ""))
    value_fen = max(0, int(template.get("value_fen", 0) or 0))
    if coupon_type in (CouponType.FULL_REDUCTION, CouponType.NO_THRESHOLD):
        return min(value_fen, total)
    if coupon_type == CouponType.DISCOUNT:
        discount_bp = int(template.get("discount_bp", 0) or 0)
        if discount_bp <= 0 or discount_bp >= FULL_DISCOUNT_BP:
            return 0
        raw = total * (FULL_DISCOUNT_BP - discount_bp) // FULL_DISCOUNT_BP
        cap = int(template.get("cap_fen", 0) or 0)
        if cap > 0:
            raw = min(raw, cap)
        raw = max(MIN_DISCOUNT_FEN, raw)
        return min(raw, total)
    return 0
