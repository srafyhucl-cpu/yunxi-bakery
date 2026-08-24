"""积分规则纯函数测试。"""

from app.service.points.rules import (
    award_points,
    points_to_fen,
    redeem_units,
    refund_reversal,
)


def test_award_points_floor_by_yuan() -> None:
    """1 元实付 = 1 分，不足 1 元向下取整。"""
    assert award_points(0) == 0
    assert award_points(99) == 0
    assert award_points(100) == 1
    assert award_points(19900) == 199
    assert award_points(-100) == 0


def test_redeem_units_floor_and_min() -> None:
    """可用积分百位向下取整，不足 100 分不可抵扣。"""
    assert redeem_units(50, 50_000, 0) == 0
    assert redeem_units(199, 50_000, 0) == 100
    assert redeem_units(1250, 50_000, 0) == 1200


def test_redeem_units_cap_50_percent_and_remain() -> None:
    """抵扣金额受 50% 上限与剩余应付约束。"""
    assert redeem_units(100_000, 10_000, 0) == 5000
    assert redeem_units(100_000, 10_000, 7_000) == 3000
    assert redeem_units(100_000, 10_000, 9_000) == 1000


def test_points_to_fen() -> None:
    """100 分 = 1 元 = 100 分钱。"""
    assert points_to_fen(0) == 0
    assert points_to_fen(100) == 100
    assert points_to_fen(1200) == 1200


def test_refund_reversal() -> None:
    """全单退款退回全部抵扣积分并收回全部已发积分。"""
    assert refund_reversal(1200, 88) == (1200, 88)
    assert refund_reversal(0, 0) == (0, 0)


def test_redeem_units_coupon_narrows_cap() -> None:
    """券先抵扣后积分上限收窄：可用 2000 分时，有券剩余应付变小。"""
    from app.service.points.rules import redeem_units

    assert redeem_units(2000, total_fen=10_000, balance_fen=0) == 2000
    assert redeem_units(2000, total_fen=10_000, balance_fen=0, coupon_fen=8000) == 2000
    assert redeem_units(2000, total_fen=10_000, balance_fen=0, coupon_fen=9000) == 1000
    assert redeem_units(2000, total_fen=10_000, balance_fen=0, coupon_fen=10_000) == 0
