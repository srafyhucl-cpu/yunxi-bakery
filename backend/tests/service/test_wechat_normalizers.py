"""四类微信 v3 Normalizer 逐字段正反向测试（B3.5，评审问题 4）。"""

import copy

import pytest

from app.service.order.wechat_normalizers import (
    PayNotifyNormalizer,
    PayQueryNormalizer,
    RefundNotifyNormalizer,
    RefundQueryNormalizer,
    WechatProtocolError,
)
from tests.fixtures import wechat_v3 as fx


def test_pay_notify_positive_extracts_v3_fields() -> None:
    """支付通知：正常报文按 v3 字段路径提取（币种取 amount.currency）。"""
    notify = PayNotifyNormalizer().normalize(copy.deepcopy(fx.PAY_NOTIFY_SUCCESS))
    assert notify.appid == "wxd678efh567hg6787"
    assert notify.mchid == "1230000109"
    assert notify.out_trade_no == "ord_b35_0001"
    assert notify.transaction_id == "4200001234202201010000000011"
    assert notify.trade_state == "SUCCESS"
    assert notify.total_fen == 888
    assert notify.currency == "CNY"


def test_pay_notify_negative_top_level_currency_rejected() -> None:
    """支付通知：币种只认 amount.currency，顶层 currency 字段无效。"""
    payload = copy.deepcopy(fx.PAY_NOTIFY_SUCCESS)
    amount = payload["amount"]
    amount["currency"] = "CNY"
    del payload["amount"]["currency"]
    payload["currency"] = "CNY"
    with pytest.raises(WechatProtocolError, match="币种"):
        PayNotifyNormalizer().normalize(payload)


def test_pay_notify_negative_wrong_currency() -> None:
    payload = copy.deepcopy(fx.PAY_NOTIFY_SUCCESS)
    payload["amount"]["currency"] = "USD"
    with pytest.raises(WechatProtocolError, match="币种不匹配"):
        PayNotifyNormalizer().normalize(payload)


@pytest.mark.parametrize(
    "field",
    ["appid", "mchid", "out_trade_no", "transaction_id", "trade_state"],
)
def test_pay_notify_negative_missing_field(field: str) -> None:
    payload = copy.deepcopy(fx.PAY_NOTIFY_SUCCESS)
    del payload[field]
    with pytest.raises(WechatProtocolError, match="缺少"):
        PayNotifyNormalizer().normalize(payload)


def test_pay_notify_negative_missing_amount() -> None:
    payload = copy.deepcopy(fx.PAY_NOTIFY_SUCCESS)
    del payload["amount"]
    with pytest.raises(WechatProtocolError, match="缺少金额"):
        PayNotifyNormalizer().normalize(payload)


def test_pay_notify_negative_non_int_total() -> None:
    payload = copy.deepcopy(fx.PAY_NOTIFY_SUCCESS)
    payload["amount"]["total"] = "88.8"
    with pytest.raises(WechatProtocolError, match="无效"):
        PayNotifyNormalizer().normalize(payload)


def test_refund_notify_positive_without_appid() -> None:
    """退款通知：不要求 appid（v3 退款报文无 appid），金额分原支付与本次退款。"""
    notify = RefundNotifyNormalizer().normalize(copy.deepcopy(fx.REFUND_NOTIFY_SUCCESS))
    assert notify.mchid == "1230000109"
    assert notify.out_refund_no == "ref_b35_0001"
    assert notify.refund_id == "5000000038202201010000000001"
    assert notify.refund_status == "SUCCESS"
    assert notify.total_fen == 888
    assert notify.refund_fen == 888
    assert notify.payer_total_fen == 888
    assert notify.payer_refund_fen == 888
    assert "appid" not in fx.REFUND_NOTIFY_SUCCESS


def test_refund_notify_negative_partial_refund_fields() -> None:
    """退款通知：原支付金额与本次退款金额分别校验（部分退款原额 != 本笔额）。"""
    payload = copy.deepcopy(fx.REFUND_NOTIFY_SUCCESS)
    payload["amount"]["refund"] = 300
    payload["amount"]["payer_refund"] = 300
    notify = RefundNotifyNormalizer().normalize(payload)
    assert notify.total_fen == 888
    assert notify.refund_fen == 300


@pytest.mark.parametrize(
    "field",
    ["mchid", "out_trade_no", "out_refund_no", "refund_id", "refund_status"],
)
def test_refund_notify_negative_missing_field(field: str) -> None:
    payload = copy.deepcopy(fx.REFUND_NOTIFY_SUCCESS)
    del payload[field]
    with pytest.raises(WechatProtocolError, match="缺少"):
        RefundNotifyNormalizer().normalize(payload)


def test_refund_notify_negative_missing_amount_refund() -> None:
    payload = copy.deepcopy(fx.REFUND_NOTIFY_SUCCESS)
    del payload["amount"]["refund"]
    with pytest.raises(WechatProtocolError, match="无效"):
        RefundNotifyNormalizer().normalize(payload)


def test_pay_query_positive() -> None:
    result = PayQueryNormalizer().normalize(copy.deepcopy(fx.PAY_QUERY_SUCCESS))
    assert result.trade_state == "SUCCESS"
    assert result.total_fen == 888
    assert result.currency == "CNY"


def test_pay_query_negative_missing_trade_state() -> None:
    payload = copy.deepcopy(fx.PAY_QUERY_SUCCESS)
    del payload["trade_state"]
    with pytest.raises(WechatProtocolError, match="缺少"):
        PayQueryNormalizer().normalize(payload)


def test_refund_query_positive_without_appid() -> None:
    result = RefundQueryNormalizer().normalize(copy.deepcopy(fx.REFUND_QUERY_SUCCESS))
    assert result.refund_status == "SUCCESS"
    assert result.total_fen == 888
    assert result.refund_fen == 888
    assert "appid" not in fx.REFUND_QUERY_SUCCESS


def test_refund_query_negative_missing_refund_id() -> None:
    payload = copy.deepcopy(fx.REFUND_QUERY_SUCCESS)
    del payload["refund_id"]
    with pytest.raises(WechatProtocolError, match="缺少"):
        RefundQueryNormalizer().normalize(payload)


def test_normalizers_independent_contracts() -> None:
    """四类 Normalizer 互不共用校验：支付报文缺 amount.currency 必失败，
    退款报文不要求 appid（两者不可互换字段合同）。"""
    pay_payload = copy.deepcopy(fx.PAY_NOTIFY_SUCCESS)
    del pay_payload["amount"]["currency"]
    with pytest.raises(WechatProtocolError):
        PayNotifyNormalizer().normalize(pay_payload)
    refund_payload = copy.deepcopy(fx.REFUND_NOTIFY_SUCCESS)
    refund_payload["appid"] = "wxd678efh567hg6787"
    notify = RefundNotifyNormalizer().normalize(refund_payload)
    assert notify.mchid == "1230000109"
