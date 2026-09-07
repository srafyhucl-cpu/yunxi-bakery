"""支付与身份上线门禁配置矩阵测试。"""

import pytest

from app import readiness
from app.config import settings
from app.models.order import Order
from app.repository.order_repo import OrderRepo
from app.service.integrations.wechat_pay import WechatPayIntegrationService
from app.service.order.payment_runtime import OrderPaymentRuntimeService

WECHAT_CREDS = {
    "WECHAT_PAY_ENABLED": True,
    "WECHAT_MINIAPP_APP_ID": "wx-app-id",
    "WECHAT_PAY_MCH_ID": "mch-id",
    "WECHAT_PAY_NOTIFY_URL": "https://pay.example/notify",
    "WECHAT_PAY_PRIVATE_KEY_PATH": "/keys/apiclient_key.pem",
    "WECHAT_PAY_CERT_SERIAL_NO": "serial-no",
    "WECHAT_PAY_API_V3_KEY": "v3-key",
}

EMPLOYEE_AUTH = {
    "WECOM_EMPLOYEE_AUTH_REQUIRED": True,
    "WECOM_EMPLOYEE_ALLOWED_USERS": "staff-1",
    "WECOM_EMPLOYEE_CORP_ID": "corp-id",
    "WECOM_EMPLOYEE_OPS_USERS": "ops-1",
}


def _apply(monkeypatch: pytest.MonkeyPatch, values: dict) -> None:
    """批量覆盖配置开关。"""
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)


def _canned_order() -> Order:
    """构造待支付订单，不依赖数据库。"""
    return Order(
        id="order-matrix-1",
        session_id="session-1",
        channel="miniapp",
        user_id="user-1",
        products="[]",
        total_amount=19.99,
        payment='{"status": "unpaid"}',
    )


def _runtime() -> OrderPaymentRuntimeService:
    """构造支付运行时，仓库在门禁分支前不触库。"""
    return OrderPaymentRuntimeService(order_repo=OrderRepo(None))


@pytest.mark.asyncio
async def test_mock_payment_requires_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未显式开启 mock 时确认接口直接拒绝，不触库。"""
    _apply(monkeypatch, {"ALLOW_MOCK_PAYMENT": False})
    with pytest.raises(ValueError, match="禁用 mock 支付"):
        await _runtime().confirm_mock_payment("order-matrix-1", user_id="user-1")


@pytest.mark.asyncio
async def test_prepare_payment_falls_back_to_mock_only_when_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """微信未就绪时仅显式 mock 环境回退，否则拒绝。"""
    for key in WECHAT_CREDS:
        monkeypatch.setattr(settings, key, "" if key != "WECHAT_PAY_ENABLED" else False)
    service = _runtime()

    async def _stub_order(self, order_id: str, user_id: str) -> Order:
        return _canned_order()

    monkeypatch.setattr(OrderPaymentRuntimeService, "_get_user_order", _stub_order)
    monkeypatch.setattr(
        OrderPaymentRuntimeService, "_wechat_pay_ready", lambda self: False
    )
    _apply(monkeypatch, {"ALLOW_MOCK_PAYMENT": True})
    session = await service.prepare_payment("order-matrix-1", user_id="user-1")
    assert session.mode == "mock"
    _apply(monkeypatch, {"ALLOW_MOCK_PAYMENT": False})
    with pytest.raises(ValueError, match="不提供 mock 支付"):
        await service.prepare_payment("order-matrix-1", user_id="user-1")


@pytest.mark.parametrize(
    ("overrides", "pay_ready", "mock_disabled"),
    [
        ({"ALLOW_MOCK_PAYMENT": False, **WECHAT_CREDS}, True, True),
        ({"ALLOW_MOCK_PAYMENT": True, **WECHAT_CREDS}, True, False),
        ({"ALLOW_MOCK_PAYMENT": False, "WECHAT_PAY_ENABLED": False}, False, True),
        (
            {
                "ALLOW_MOCK_PAYMENT": False,
                **WECHAT_CREDS,
                "WECHAT_PAY_NOTIFY_URL": "",
            },
            False,
            True,
        ),
        (
            {
                "ALLOW_MOCK_PAYMENT": False,
                **WECHAT_CREDS,
                "WECHAT_PAY_API_V3_KEY": "",
            },
            False,
            True,
        ),
    ],
)
def test_payment_config_matrix(
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict,
    pay_ready: bool,
    mock_disabled: bool,
) -> None:
    """开发、测试、生产、缺凭证四态门禁矩阵。"""
    _apply(monkeypatch, overrides)
    assert WechatPayIntegrationService().is_ready() is pay_ready
    checks = readiness.build_channel_readiness_checks()
    assert checks["wechat_pay_configured"] is pay_ready
    assert checks["mock_payment_disabled"] is mock_disabled


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"WECOM_STAFF_ID": "", "WECOM_KF_SERVICER_USERID": ""}, False),
        ({"WECOM_STAFF_ID": "staff-1"}, True),
        ({"WECOM_STAFF_ID": "", "WECOM_KF_SERVICER_USERID": "servicer-1"}, True),
        ({**EMPLOYEE_AUTH}, True),
        ({**EMPLOYEE_AUTH, "WECOM_EMPLOYEE_AUTH_REQUIRED": False}, False),
        ({**EMPLOYEE_AUTH, "WECOM_EMPLOYEE_ALLOWED_USERS": ""}, False),
        ({**EMPLOYEE_AUTH, "WECOM_EMPLOYEE_CORP_ID": ""}, False),
        ({**EMPLOYEE_AUTH, "WECOM_EMPLOYEE_OPS_USERS": ""}, False),
    ],
)
def test_handoff_and_employee_auth_matrix(
    monkeypatch: pytest.MonkeyPatch, overrides: dict, expected: bool
) -> None:
    """接手人与员工鉴权配置矩阵，缺任一项即阻断。"""
    _apply(monkeypatch, overrides)
    checks = readiness.build_channel_readiness_checks()
    if "WECOM_STAFF_ID" in overrides or "WECOM_KF_SERVICER_USERID" in overrides:
        assert checks["handoff_staff_userid_ready"] is expected
    else:
        assert checks["wecom_employee_auth_ready"] is expected
