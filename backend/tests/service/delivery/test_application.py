"""配送领域内部金额和状态契约测试。"""

from app.models.delivery import (
    DeliveryQuoteStatus,
    FulfillmentMethod,
    build_payable_fen,
    can_pay_quote,
)


def test_build_payable_fen_includes_delivery_fee() -> None:
    assert build_payable_fen(19800, 2600, 1000, 500, 200, 0) == 20700


def test_pickup_quote_with_zero_fee_can_be_paid() -> None:
    assert can_pay_quote(DeliveryQuoteStatus.QUOTED, 0) is True
    assert FulfillmentMethod.PICKUP.value == "pickup"


def test_pending_delivery_quote_cannot_be_paid_without_fee() -> None:
    assert can_pay_quote(DeliveryQuoteStatus.PENDING_CONFIRMATION, None) is False
    assert can_pay_quote(DeliveryQuoteStatus.PROVIDER_UNAVAILABLE, None) is False


def test_negative_money_is_rejected() -> None:
    try:
        build_payable_fen(100, -1)
    except ValueError as exc:
        assert str(exc) == "金额不能为负数"
    else:
        raise AssertionError("负数金额应被拒绝")
