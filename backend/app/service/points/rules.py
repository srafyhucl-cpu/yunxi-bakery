"""积分业务规则纯函数（无 IO，可独立单测）。"""

MIN_REDEEM_POINTS = 100
MAX_REDEEM_RATIO_NUMERATOR = 50
MAX_REDEEM_RATIO_DENOMINATOR = 100


def award_points(cash_fen: int) -> int:
    """按实付现金（分）计算应发积分：1 元实付 = 1 分，向下取整。"""
    return max(0, cash_fen) // 100


def points_to_fen(points_used: int) -> int:
    """把抵扣积分数折算为金额（分）：100 分 = 1 元。"""
    return max(0, points_used) // 100 * 100


def redeem_units(
    available_points: int,
    total_fen: int,
    balance_fen: int,
    coupon_fen: int = 0,
) -> int:
    """计算本单可用抵扣积分数。

    规则：百位向下取整；单笔最低 100 分；最高抵扣订单应付 50%，
    且折算金额不超过剩余应付（total_fen - balance_fen - coupon_fen）。
    """
    available = max(0, available_points)
    usable = (available // MIN_REDEEM_POINTS) * MIN_REDEEM_POINTS
    if usable < MIN_REDEEM_POINTS:
        return 0
    cap_fen = max(0, total_fen - balance_fen - max(0, coupon_fen))
    ratio_cap_fen = (
        total_fen * MAX_REDEEM_RATIO_NUMERATOR // MAX_REDEEM_RATIO_DENOMINATOR
    )
    points_fen = points_to_fen(min(cap_fen, ratio_cap_fen))
    return min(usable, points_fen)


def refund_reversal(points_used: int, points_awarded: int) -> tuple[int, int]:
    """全单退款退返金额：返回（退回抵扣积分, 收回已发积分）。"""
    return max(0, points_used), max(0, points_awarded)
