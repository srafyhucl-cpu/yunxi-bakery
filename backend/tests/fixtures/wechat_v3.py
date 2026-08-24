"""微信支付 v3 真实报文 fixture（B3.5，评审问题 4）。

结构按微信支付 v3 API 文档组织，供四类 Normalizer 逐字段正反向测试使用。
"""

PAY_NOTIFY_SUCCESS = {
    "appid": "wxd678efh567hg6787",
    "mchid": "1230000109",
    "out_trade_no": "ord_b35_0001",
    "transaction_id": "4200001234202201010000000011",
    "trade_type": "JSAPI",
    "trade_state": "SUCCESS",
    "trade_state_desc": "支付成功",
    "bank_type": "CMC",
    "attach": "",
    "success_time": "2026-08-15T12:00:00+08:00",
    "payer": {"openid": "oUpF8uMuAJO_M2pxb1Q9zNjWeS6o"},
    "amount": {
        "total": 888,
        "payer_total": 888,
        "currency": "CNY",
        "payer_currency": "CNY",
    },
}

REFUND_NOTIFY_SUCCESS = {
    "mchid": "1230000109",
    "out_trade_no": "ord_b35_0001",
    "transaction_id": "4200001234202201010000000011",
    "out_refund_no": "ref_b35_0001",
    "refund_id": "5000000038202201010000000001",
    "refund_status": "SUCCESS",
    "success_time": "2026-08-15T13:00:00+08:00",
    "amount": {
        "total": 888,
        "refund": 888,
        "payer_total": 888,
        "payer_refund": 888,
    },
    "user_received_account": "招商银行信用卡0403",
}

PAY_QUERY_SUCCESS = {
    "appid": "wxd678efh567hg6787",
    "mchid": "1230000109",
    "out_trade_no": "ord_b35_0001",
    "transaction_id": "4200001234202201010000000011",
    "trade_type": "JSAPI",
    "trade_state": "SUCCESS",
    "trade_state_desc": "支付成功",
    "bank_type": "CMC",
    "attach": "",
    "success_time": "2026-08-15T12:00:00+08:00",
    "payer": {"openid": "oUpF8uMuAJO_M2pxb1Q9zNjWeS6o"},
    "amount": {
        "total": 888,
        "payer_total": 888,
        "currency": "CNY",
        "payer_currency": "CNY",
    },
}

REFUND_QUERY_SUCCESS = {
    "mchid": "1230000109",
    "out_trade_no": "ord_b35_0001",
    "transaction_id": "4200001234202201010000000011",
    "out_refund_no": "ref_b35_0001",
    "refund_id": "5000000038202201010000000001",
    "refund_status": "SUCCESS",
    "success_time": "2026-08-15T13:00:00+08:00",
    "amount": {
        "total": 888,
        "refund": 888,
        "payer_total": 888,
        "payer_refund": 888,
    },
}
