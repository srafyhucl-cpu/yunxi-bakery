"""小程序支付兼容入口。"""

from app.service.integrations.wechat_pay import settings
from app.service.order.payment_runtime import (
    PAYMENT_SIGN_TYPE,
    WECHAT_PAY_SUCCESS_STATE,
    OrderPaymentRuntimeService as MiniappPaymentService,
    WechatPayPrepayResult,
)
from app.service.order.payment_state import (
    PAYMENT_METHOD_MOCK,
    PAYMENT_METHOD_WECHAT,
    PAYMENT_MODE_MOCK,
    PAYMENT_MODE_WECHAT,
    PAYMENT_STATUS_EXPIRED,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_UNPAID,
    PAYMENT_TIMEOUT_MINUTES,
    PaymentSession,
    TIME_FORMAT,
    build_initial_payment,
    build_mock_payment_session,
)


__all__ = [
    "MiniappPaymentService",
    "PAYMENT_METHOD_MOCK",
    "PAYMENT_METHOD_WECHAT",
    "PAYMENT_MODE_MOCK",
    "PAYMENT_MODE_WECHAT",
    "PAYMENT_SIGN_TYPE",
    "PAYMENT_STATUS_EXPIRED",
    "PAYMENT_STATUS_PAID",
    "PAYMENT_STATUS_UNPAID",
    "PAYMENT_TIMEOUT_MINUTES",
    "PaymentSession",
    "TIME_FORMAT",
    "WECHAT_PAY_SUCCESS_STATE",
    "WechatPayPrepayResult",
    "build_initial_payment",
    "build_mock_payment_session",
    "settings",
]
