"""小程序支付 API 测试。"""

import aiosqlite
import base64
import json

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import FastAPI

from app.api.miniapp_payments import create_miniapp_payments_router
from app.repository.config_repo import ConfigRepo
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order import OrderApplicationService
from tests.helpers.miniapp_catalog_seed import seed_miniapp_product


@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    """构建只包含小程序支付路由的测试应用。"""
    test_app = FastAPI()
    service = OrderApplicationService(
        order_repo=OrderRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )
    test_app.include_router(create_miniapp_payments_router(service))
    return test_app


@pytest.mark.asyncio
async def test_miniapp_payment_notify_rejects_bad_signature(app: FastAPI) -> None:
    """微信支付通知签名无效时应拒绝。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/payments/wechat/notify",
            content=b"{}",
            headers={
                "wechatpay-timestamp": "1",
                "wechatpay-nonce": "nonce",
                "wechatpay-signature": "bad",
                "wechatpay-serial": "serial",
                "content-type": "application/json",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "微信支付通知签名无效"


@pytest.mark.asyncio
async def test_miniapp_payment_notify_marks_order_paid(
    db: aiosqlite.Connection,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """微信支付通知应回写订单支付状态。"""
    await seed_miniapp_product(
        db,
        item_id=83001,
        title="微信通知蛋糕",
        price_fen=19800,
        stock=1,
    )
    service = OrderApplicationService(
        order_repo=OrderRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )
    created = await service.create_order(
        {
            "items": [
                {
                    "productId": "83001",
                    "title": "微信通知蛋糕",
                    "priceFen": 19800,
                    "quantity": 1,
                }
            ],
            "expectTime": "2026-06-18 18:00",
        },
        user_id="wx_notify_openid",
    )

    service = OrderApplicationService(
        order_repo=OrderRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )
    monkeypatch.setattr(
        "app.service.order.payment_runtime.settings.WECHAT_PAY_MCH_ID", "mch-test"
    )
    monkeypatch.setattr(
        "app.service.order.payment_runtime.settings.WECHAT_MINIAPP_APP_ID",
        "appid-test",
    )
    payload = {
        "id": "notify-1",
        "resource": {
            "algorithm": "AEAD_AES_256_GCM",
            "ciphertext": "",
            "nonce": "testnonce123456",
            "associated_data": "transaction",
        },
    }
    aesgcm = AESGCM(b"1" * 32)
    plaintext = json.dumps(
        {
            "out_trade_no": created["orderId"],
            "trade_state": "SUCCESS",
            "mchid": "mch-test",
            "appid": "appid-test",
            # B3.5（评审问题 4）：币种在 amount.currency，顶层无 currency（真实 v3 报文）
            "amount": {"total": 19800, "currency": "CNY"},
            "transaction_id": "4200000000202606171234567890",
            "success_time": "2026-06-17T12:00:00+08:00",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    payload["resource"]["ciphertext"] = base64.b64encode(
        aesgcm.encrypt(
            payload["resource"]["nonce"].encode("utf-8"),
            plaintext,
            payload["resource"]["associated_data"].encode("utf-8"),
        )
    ).decode("utf-8")

    monkeypatch.setattr(
        "app.service.integrations.wechat_pay.settings.WECHAT_PAY_PLATFORM_CERT_PATH",
        "D:/missing/platform-cert.pem",
    )
    monkeypatch.setattr(
        "app.service.order.payment_runtime.OrderPaymentRuntimeService._verify_wechat_notify_signature",
        lambda self, raw_body, headers: True,
    )
    monkeypatch.setattr(
        "app.service.order.payment_runtime.OrderPaymentRuntimeService._decrypt_wechat_resource",
        lambda self, resource: {
            "out_trade_no": created["orderId"],
            "trade_state": "SUCCESS",
            "mchid": "mch-test",
            "appid": "appid-test",
            "amount": {"total": 19800, "currency": "CNY"},
            "transaction_id": "4200000000202606171234567890",
            "success_time": "2026-06-17T12:00:00+08:00",
        },
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/miniapp/payments/wechat/notify",
            content=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 200
    assert response.json()["code"] == "SUCCESS"
    detail = await service.get_user_order(
        created["orderId"], user_id="wx_notify_openid"
    )
    assert detail["paymentStatus"] == "paid"
    assert detail["paymentMethod"] == "wechat"
    assert detail["paymentPaidAt"] == "2026-06-17 12:00:00"

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        duplicate = await client.post(
            "/api/v1/miniapp/payments/wechat/notify",
            content=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
        )
    assert duplicate.status_code == 200
