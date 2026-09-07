"""微信支付通知新鲜度与 intake 幂等测试。"""

import json

import aiosqlite
import pytest

from app.models.order import Order, OrderStatus
from app.repository.config_repo import ConfigRepo
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.integrations.wechat_pay import (
    NOTIFY_FUTURE_SKEW_SECONDS,
    NOTIFY_MAX_AGE_SECONDS,
    WechatPayIntegrationService,
    _is_notify_timestamp_fresh,
)
from app.service.order import OrderApplicationService
from app.service.order.notify_intake import (
    archive_notify,
    build_notify_key,
    extract_notify_identity,
)

NOW = 1_786_000_000


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (str(NOW), True),
        (str(NOW - NOTIFY_MAX_AGE_SECONDS), True),
        (str(NOW - NOTIFY_MAX_AGE_SECONDS - 1), False),
        (str(NOW - 86400), False),
        (str(NOW + 1), True),
        (str(NOW + NOTIFY_FUTURE_SKEW_SECONDS), True),
        (str(NOW + NOTIFY_FUTURE_SKEW_SECONDS + 1), False),
        ("", False),
        ("not-a-number", False),
    ],
)
def test_notify_timestamp_freshness_boundary(timestamp: str, expected: bool) -> None:
    """时间戳过旧或超前均拒绝，边界精确到秒。"""
    assert _is_notify_timestamp_fresh(timestamp, now_seconds=NOW) is expected


def test_verify_rejects_stale_timestamp_without_cert() -> None:
    """缺凭证时直接拒绝，不触及密码学路径。"""
    assert (
        WechatPayIntegrationService().verify_notify_signature(
            b"{}",
            {
                "wechatpay-timestamp": str(NOW - 3600),
                "wechatpay-nonce": "nonce",
                "wechatpay-signature": "sig",
                "wechatpay-serial": "serial",
            },
            now_seconds=NOW,
        )
        is False
    )


def test_extract_notify_identity_rejects_missing_id() -> None:
    """缺少事件标识直接拒绝，无法去重不消费。"""
    with pytest.raises(ValueError, match="事件标识"):
        extract_notify_identity({"event_type": "TRANSACTION.SUCCESS"})
    event_id, event_type = extract_notify_identity(
        {"id": "EV-1", "event_type": "TRANSACTION.SUCCESS"}
    )
    assert (event_id, event_type) == ("EV-1", "TRANSACTION.SUCCESS")
    assert build_notify_key("EV-1") == "wechat_pay_notify:EV-1"


def _service(db: aiosqlite.Connection) -> OrderApplicationService:
    """构造订单应用服务，仓库直连用例数据库。"""
    return OrderApplicationService(
        order_repo=OrderRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )


def _pay_payload(order_id: str, total_fen: int = 19800) -> dict:
    """构造已解密的交易成功事务体。"""
    return {
        "out_trade_no": order_id,
        "trade_state": "SUCCESS",
        "mchid": "mch-test",
        "appid": "appid-test",
        "amount": {"total": total_fen, "currency": "CNY"},
        "transaction_id": "4200000000202606171234567890",
        "success_time": "2026-06-17T12:00:00+08:00",
    }


async def _seed_paid_order(
    db: aiosqlite.Connection, order_id: str, total_yuan: float = 198.00
) -> None:
    """直写已支付订单，腿为空，聚焦通知链路。"""
    await db.execute(
        "INSERT OR IGNORE INTO sessions (id, channel, user_id, status) "
        "VALUES (?, ?, ?, ?)",
        ("session-1", "miniapp", "wx_openid_notify", "active"),
    )
    await OrderRepo(db).create_order(
        Order(
            id=order_id,
            session_id="session-1",
            channel="miniapp",
            user_id="wx_openid_notify",
            products="[]",
            total_amount=total_yuan,
            delivery="{}",
            payment=json.dumps(
                {
                    "status": "paid",
                    "method": "wechat",
                    "paidAt": "2026-06-17 12:00:00",
                    "transactionId": "4200000000202606171234567890",
                    "couponFen": 0,
                    "balanceFen": 0,
                    "pointsFen": 0,
                }
            ),
            status=OrderStatus.PENDING,
            remark="",
            created_at="2026-06-17 11:00:00",
            updated_at="2026-06-17 12:00:00",
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_archive_is_idempotent_in_caller_transaction(
    db: aiosqlite.Connection,
) -> None:
    """同一事件重复归档返回已存在，不抛错。"""
    repo_db = db
    assert await archive_notify(repo_db, "EV-dup", {"id": "EV-dup"}) is True
    assert await archive_notify(repo_db, "EV-dup", {"id": "EV-dup"}) is False
    rows = await db.execute_fetchall(
        "SELECT status FROM inbox_events WHERE message_key = ?",
        ("wechat_pay_notify:EV-dup",),
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_duplicate_query_recovery_confirms_once(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同一查询恢复重复执行只落账一次，收件箱单行。"""
    await _seed_paid_order(db, "order-dup-1")
    monkeypatch.setattr(
        "app.service.order.payment_runtime.settings.WECHAT_PAY_MCH_ID", "mch-test"
    )
    monkeypatch.setattr(
        "app.service.order.payment_runtime.settings.WECHAT_MINIAPP_APP_ID",
        "appid-test",
    )
    service = _service(db)
    payload = _pay_payload("order-dup-1")
    first = await service.reconcile_pay_from_query(payload)
    second = await service.reconcile_pay_from_query(payload)
    assert first["paymentStatus"] == "paid"
    assert second["paymentStatus"] == "paid"
    rows = await db.execute_fetchall(
        "SELECT status FROM inbox_events WHERE message_key = ?",
        ("wechat_pay_notify:query:pay:order-dup-1:4200000000202606171234567890",),
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_query_before_notify_is_order_safe(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """查询先恢复、通知逻辑后到达，乱序不产生双重落账。"""
    await _seed_paid_order(db, "order-ooo-1", total_yuan=100.00)
    monkeypatch.setattr(
        "app.service.order.payment_runtime.settings.WECHAT_PAY_MCH_ID", "mch-test"
    )
    monkeypatch.setattr(
        "app.service.order.payment_runtime.settings.WECHAT_MINIAPP_APP_ID",
        "appid-test",
    )
    service = _service(db)
    payload = _pay_payload("order-ooo-1", total_fen=10000)
    await service.reconcile_pay_from_query(payload)
    await service.reconcile_pay_from_query(payload)
    detail = await service.get_user_order("order-ooo-1", user_id="wx_openid_notify")
    assert detail["paymentStatus"] == "paid"


@pytest.mark.asyncio
async def test_pay_notify_then_query_single_settlement(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """通知先落账、查询后到达，共用交易号只结算一次。"""
    await _seed_paid_order(db, "order-noq-1", total_yuan=100.00)
    monkeypatch.setattr(
        "app.service.order.payment_runtime.settings.WECHAT_PAY_MCH_ID", "mch-test"
    )
    monkeypatch.setattr(
        "app.service.order.payment_runtime.settings.WECHAT_MINIAPP_APP_ID",
        "appid-test",
    )
    transaction = _pay_payload("order-noq-1", total_fen=10000)
    monkeypatch.setattr(
        "app.service.order.payment_runtime.OrderPaymentRuntimeService"
        "._verify_wechat_notify_signature",
        lambda self, raw_body, headers: True,
    )
    monkeypatch.setattr(
        "app.service.order.payment_runtime.OrderPaymentRuntimeService"
        "._decrypt_wechat_resource",
        lambda self, resource: transaction,
    )
    service = _service(db)
    raw_body = json.dumps({"id": "EV-noq-1", "resource": {}}).encode("utf-8")
    first = await service.handle_wechat_payment_notify(raw_body=raw_body, headers={})
    assert first["paymentStatus"] == "paid"
    second = await service.handle_wechat_payment_notify(raw_body=raw_body, headers={})
    assert second.get("duplicate") is True
    third = await service.reconcile_pay_from_query(transaction)
    assert third["paymentStatus"] == "paid"
    rows = await db.execute_fetchall(
        "SELECT message_key FROM inbox_events WHERE queue_name = ?",
        ("wechat_pay_notify",),
    )
    assert len(rows) == 2
