"""券规则纯函数测试：可用性、抵扣、最新态。"""

from app.service.coupon.rules import calc_discount, is_coupon_available


def _tpl(**overrides: object) -> dict:
    base = {
        "id": "cg_001",
        "name": "满30减5",
        "coupon_type": "FULL_REDUCTION",
        "threshold_fen": 3000,
        "value_fen": 500,
        "discount_bp": 0,
        "cap_fen": 0,
        "valid_from": "2026-08-01",
        "valid_until": "2026-09-30",
        "status": "active",
    }
    base.update(overrides)
    return base


def test_full_reduction_available_and_discount() -> None:
    tpl = _tpl()
    assert is_coupon_available(tpl, total_fen=3000, now_text="2026-08-10 12:00:00")
    assert not is_coupon_available(tpl, total_fen=2999, now_text="2026-08-10 12:00:00")
    assert calc_discount(tpl, total_fen=4000) == 500


def test_no_threshold_discount_capped() -> None:
    tpl = _tpl(coupon_type="NO_THRESHOLD", threshold_fen=0, value_fen=800)
    assert calc_discount(tpl, total_fen=500) == 500
    assert calc_discount(tpl, total_fen=1000) == 800


def test_discount_type_floor_and_cap() -> None:
    tpl = _tpl(coupon_type="DISCOUNT", discount_bp=9000, cap_fen=300)
    assert calc_discount(tpl, total_fen=10_000) == 300
    assert calc_discount(tpl, total_fen=1000) == 100
    assert is_coupon_available(tpl, total_fen=100, now_text="2026-08-10 12:00:00")


def test_validity_range() -> None:
    tpl = _tpl()
    assert not is_coupon_available(tpl, total_fen=4000, now_text="2026-07-31 23:59:59")
    assert not is_coupon_available(tpl, total_fen=4000, now_text="2026-10-01 00:00:00")
    assert not is_coupon_available(
        _tpl(status="disabled"), total_fen=4000, now_text="2026-08-10 12:00:00"
    )
