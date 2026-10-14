"""核心订单闭环候选问题测试。"""

import json

import aiosqlite
import pytest

from app.config import settings
from app.models.order import Order, OrderStatus
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.config_repo import ConfigRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order import OrderApplicationService
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import loads_payment
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
    StoredValueService,
)
from tests.helpers.legacy_order_catalog import (
    LegacyOrderInventoryRepo,
    LegacyOrderProductRepo,
)


def _service(db: aiosqlite.Connection) -> OrderApplicationService:
    return OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )


def test_payment_runtime_can_be_constructed_before_request_context() -> None:
    """服务应在应用 lifespan 装配期构造，不能提前解析请求数据库句柄。"""
    OrderPaymentRuntimeService(OrderRepo(None))


@pytest.mark.asyncio
async def test_admin_status_update_does_not_overwrite_concurrent_timeout_close(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """后台读到待支付后发生超时关单时，不得再把取消终态推进为已确认。"""
    order_id = "order-status-race"
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status) VALUES (?, ?, ?, ?)",
        ("session-status-race", "miniapp", "wx_status_race", "active"),
    )
    order_repo = OrderRepo(db)
    await order_repo.create_order(
        Order(
            id=order_id,
            session_id="session-status-race",
            channel="miniapp",
            user_id="wx_status_race",
            products="[]",
            total_amount=198.00,
            delivery="{}",
            payment=json.dumps(
                {
                    "status": "unpaid",
                    "method": "",
                    "paidAt": "",
                    "expiredAt": "",
                    "expiredReason": "",
                    "createdAt": "2026-09-25 11:00:00",
                }
            ),
            status=OrderStatus.PENDING,
            remark="",
            created_at="2026-09-25 11:00:00",
            updated_at="2026-09-25 11:00:00",
        )
    )
    await db.commit()

    service = _service(db)
    admin_status_service = service._admin_status_service
    expiration_service = service._expiration_service
    original_get_order = OrderRepo.get_order
    has_expired = False

    async def get_order_then_expire(
        repo: OrderRepo,
        order_id: str,
    ) -> Order | None:
        nonlocal has_expired
        order = await original_get_order(repo, order_id)
        if not has_expired and order is not None and order.id == order_id:
            has_expired = True
            await expiration_service.expire_unpaid_order(order.id)
        return order

    monkeypatch.setattr(OrderRepo, "get_order", get_order_then_expire)

    update_error = ""
    try:
        await admin_status_service.update_admin_order_status(order_id, "confirmed")
    except ValueError as exc:
        update_error = str(exc)
    await db.commit()

    latest = await order_repo.get_order(order_id)
    events = await OrderEventRepo(db).list_by_order(order_id)
    assert latest is not None
    assert latest.status == OrderStatus.CANCELLED
    assert loads_payment(latest.payment)["status"] == "expired"
    assert "当前订单状态不允许" in update_error
    event_statuses = [event.status for event in events]
    assert OrderStatus.CANCELLED.value in event_statuses
    assert OrderStatus.CONFIRMED.value not in event_statuses


@pytest.mark.asyncio
async def test_late_wechat_payment_after_timeout_is_recorded_for_refund(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超时关单后的微信到账必须记录取消终态和待退款事实。"""
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status) VALUES (?, ?, ?, ?)",
        ("session-late-timeout", "miniapp", "wx_openid_timeout", "active"),
    )
    order = Order(
        id="order-late-timeout",
        session_id="session-late-timeout",
        channel="miniapp",
        user_id="wx_openid_timeout",
        products="[]",
        total_amount=198.00,
        delivery="{}",
        payment=json.dumps(
            {
                "status": "unpaid",
                "method": "",
                "couponFen": 0,
                "balanceFen": 0,
                "pointsFen": 0,
            }
        ),
        status=OrderStatus.PENDING,
        remark="",
        created_at="2026-06-18 11:00:00",
        updated_at="2026-06-18 11:00:00",
    )
    order_repo = OrderRepo(db)
    await order_repo.create_order(order)
    await db.commit()

    service = _service(db)
    expired = await service.expire_unpaid_order(order.id)
    assert expired["status"] == OrderStatus.CANCELLED.value
    assert expired["paymentStatus"] == "expired"

    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-test")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-test")
    transaction = {
        "out_trade_no": order.id,
        "trade_state": "SUCCESS",
        "mchid": "mch-test",
        "appid": "appid-test",
        "amount": {"total": 19800, "currency": "CNY"},
        "transaction_id": "4200000000202606181234567896",
        "success_time": "2026-06-18T12:00:00+08:00",
    }
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
    raw_body = json.dumps({"id": "EV-late-timeout", "resource": {}}).encode("utf-8")

    result = await service.handle_wechat_payment_notify(
        raw_body=raw_body,
        headers={},
    )

    assert result["status"] == OrderStatus.CANCELLED.value
    assert result["paymentStatus"] == "paid"
    assert result["paymentRefundStatus"] == "pending"
    latest = await order_repo.get_order(order.id)
    assert latest is not None
    payment = loads_payment(latest.payment)
    assert payment["transactionId"] == transaction["transaction_id"]
    assert payment["refundAmountFen"] == 19800


@pytest.mark.asyncio
async def test_refund_before_late_payment_still_binds_combined_external_leg(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """组合支付退款先到后，迟到支付仍必须绑定外部微信交易事实。"""
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '组合支付乱序', 'high', 1)",
        ("cm-core-r12", "13800000012"),
    )
    await db.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        ("cil-core-r12", "cm-core-r12", "openid-core-r12", "openid-core-r12"),
    )
    await db.execute(
        "INSERT INTO member_balance (mobile, stored_value_fen) VALUES (?, ?)",
        ("13800000012", 10000),
    )
    await db.commit()

    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    order_repo = OrderRepo(db)
    stored_value_service = StoredValueService(
        member_service=member_service,
        payment_service=StoredValueOrderPaymentService(
            order_repo=order_repo,
            member_service=member_service,
        ),
    )
    service = OrderApplicationService(
        order_repo=order_repo,
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=LegacyOrderProductRepo(db),
        inventory_repo=LegacyOrderInventoryRepo(db),
        config_repo=ConfigRepo(db),
        stored_value_service=stored_value_service,
    )
    created = await service.create_order(
        {
            "items": [
                {
                    "productId": "p_core_r12",
                    "title": "组合支付乱序蛋糕",
                    "priceFen": 19800,
                    "quantity": 1,
                }
            ],
            "receiverName": "组合支付乱序",
            "receiverPhone": "13800000012",
            "deliveryType": "pickup",
            "expectTime": "2026-09-25 19:00",
        },
        user_id="wx_openid-core-r12",
    )
    order_id = created["orderId"]
    await stored_value_service.prepare_combined_payment(
        order_id,
        user_id="wx_openid-core-r12",
        balance_fen=2000,
    )
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-core-r12")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-core-r12")

    refund = await service.reconcile_refund_from_query(
        {
            "mchid": "mch-core-r12",
            "out_trade_no": order_id,
            "transaction_id": "wx-core-r12",
            "out_refund_no": "R-core-r12",
            "refund_id": "refund-core-r12",
            "refund_status": "SUCCESS",
            "success_time": "2026-09-25T12:05:00+08:00",
            "amount": {
                "total": 17800,
                "refund": 17800,
                "payer_total": 17800,
                "payer_refund": 17800,
            },
        },
        payer_total_fen=17800,
    )
    assert refund["kind"] == "acknowledged"

    payment = await service.reconcile_pay_from_query(
        {
            "out_trade_no": order_id,
            "mchid": "mch-core-r12",
            "appid": "appid-core-r12",
            "trade_state": "SUCCESS",
            "amount": {"total": 17800, "currency": "CNY"},
            "transaction_id": "wx-core-r12",
            "success_time": "2026-09-25T12:00:00+08:00",
        }
    )

    assert payment["paymentStatus"] == "paid"
    latest = await order_repo.get_order(order_id)
    assert latest is not None
    latest_payment = loads_payment(latest.payment)
    assert latest_payment["status"] == "paid"
    assert latest_payment["transactionId"] == "wx-core-r12"
    assert latest_payment["refundStatus"] == "full"
    transaction_rows = await db.execute_fetchall(
        "SELECT order_id FROM payment_transactions WHERE transaction_id = ?",
        ("wx-core-r12",),
    )
    assert [dict(row) for row in transaction_rows] == [{"order_id": order_id}]


@pytest.mark.asyncio
async def test_late_payment_rejects_transaction_mismatch_after_refund_first(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """退款先到后，迟到支付必须绑定退款事实中的同一微信交易号。"""
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status) VALUES (?, ?, ?, ?)",
        ("session-refund-mismatch", "miniapp", "wx_refund_mismatch", "active"),
    )
    order_repo = OrderRepo(db)
    await order_repo.create_order(
        Order(
            id="order-refund-mismatch",
            session_id="session-refund-mismatch",
            channel="miniapp",
            user_id="wx_refund_mismatch",
            products="[]",
            total_amount=198.00,
            delivery="{}",
            payment=json.dumps(
                {
                    "status": "unpaid",
                    "method": "",
                    "couponFen": 0,
                    "balanceFen": 0,
                    "pointsFen": 0,
                    "pointsUsed": 0,
                    "createdAt": "2026-09-25 11:00:00",
                }
            ),
            status=OrderStatus.PENDING,
            remark="",
            created_at="2026-09-25 11:00:00",
            updated_at="2026-09-25 11:00:00",
        )
    )
    await db.commit()
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-refund-mismatch")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-refund-mismatch")

    service = _service(db)
    refund = await service.reconcile_refund_from_query(
        {
            "mchid": "mch-refund-mismatch",
            "out_trade_no": "order-refund-mismatch",
            "transaction_id": "wx-refund-transaction",
            "out_refund_no": "R-refund-mismatch",
            "refund_id": "refund-mismatch",
            "refund_status": "SUCCESS",
            "success_time": "2026-09-25T12:05:00+08:00",
            "amount": {
                "total": 19800,
                "refund": 19800,
                "payer_total": 19800,
                "payer_refund": 19800,
            },
        },
        payer_total_fen=19800,
    )
    assert refund["kind"] == "acknowledged"

    with pytest.raises(ValueError, match="退款交易号与订单不一致"):
        await service.reconcile_pay_from_query(
            {
                "out_trade_no": "order-refund-mismatch",
                "mchid": "mch-refund-mismatch",
                "appid": "appid-refund-mismatch",
                "trade_state": "SUCCESS",
                "amount": {"total": 19800, "currency": "CNY"},
                "transaction_id": "wx-other-payment-transaction",
                "success_time": "2026-09-25T12:00:00+08:00",
            }
        )

    latest = await order_repo.get_order("order-refund-mismatch")
    assert latest is not None
    latest_payment = loads_payment(latest.payment)
    assert latest_payment["status"] == "unpaid"
    assert latest_payment.get("transactionId", "") == ""
    assert latest_payment["refundStatus"] == "full"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("refund_status", "refund_fen"),
    [("full", 17800), ("over", 18000)],
)
async def test_cancelled_refunded_partial_order_keeps_full_refund_fact(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
    refund_status: str,
    refund_fen: int,
) -> None:
    """退款终态完成后先关单，迟到支付不得把退款终态改回待退款。"""
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status) VALUES (?, ?, ?, ?)",
        ("session-cancelled-refund", "miniapp", "wx_cancelled_refund", "active"),
    )
    order_repo = OrderRepo(db)
    await order_repo.create_order(
        Order(
            id="order-cancelled-refund",
            session_id="session-cancelled-refund",
            channel="miniapp",
            user_id="wx_cancelled_refund",
            products="[]",
            total_amount=198.00,
            delivery="{}",
            payment=json.dumps(
                {
                    "status": "partial",
                    "method": "combined",
                    "balanceFen": 2000,
                    "remainFen": 17800,
                    "couponFen": 0,
                    "pointsFen": 0,
                    "pointsUsed": 0,
                    "refundStatus": refund_status,
                    "refundFen": refund_fen,
                    "createdAt": "2026-09-25 11:00:00",
                }
            ),
            status=OrderStatus.CANCELLED,
            remark="",
            created_at="2026-09-25 11:00:00",
            updated_at="2026-09-25 11:30:00",
        )
    )
    await db.commit()
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-cancelled-refund")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-cancelled-refund")

    result = await _service(db).reconcile_pay_from_query(
        {
            "out_trade_no": "order-cancelled-refund",
            "mchid": "mch-cancelled-refund",
            "appid": "appid-cancelled-refund",
            "trade_state": "SUCCESS",
            "amount": {"total": 17800, "currency": "CNY"},
            "transaction_id": "wx-cancelled-refund",
            "success_time": "2026-09-25T12:00:00+08:00",
        }
    )

    assert result["paymentStatus"] == "paid"
    latest = await order_repo.get_order("order-cancelled-refund")
    assert latest is not None
    payment = loads_payment(latest.payment)
    assert payment["status"] == "paid"
    assert payment["refundStatus"] == refund_status
    assert payment["refundFen"] == refund_fen
    assert payment["transactionId"] == "wx-cancelled-refund"


@pytest.mark.asyncio
async def test_cancelled_partially_refunded_order_keeps_refund_fact(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """部分退款先到并关单后，迟到支付不得把退款事实改成待退款。"""
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status) VALUES (?, ?, ?, ?)",
        ("session-cancelled-partial-refund", "miniapp", "wx_partial_refund", "active"),
    )
    order_repo = OrderRepo(db)
    await order_repo.create_order(
        Order(
            id="order-cancelled-partial-refund",
            session_id="session-cancelled-partial-refund",
            channel="miniapp",
            user_id="wx_partial_refund",
            products="[]",
            total_amount=198.00,
            delivery="{}",
            payment=json.dumps(
                {
                    "status": "partial",
                    "method": "combined",
                    "balanceFen": 2000,
                    "remainFen": 17800,
                    "couponFen": 0,
                    "pointsFen": 0,
                    "pointsUsed": 0,
                    "refundStatus": "partial",
                    "refundFen": 8000,
                    "createdAt": "2026-09-25 11:00:00",
                }
            ),
            status=OrderStatus.CANCELLED,
            remark="",
            created_at="2026-09-25 11:00:00",
            updated_at="2026-09-25 11:30:00",
        )
    )
    await db.commit()
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-cancelled-partial-refund")
    monkeypatch.setattr(
        settings, "WECHAT_MINIAPP_APP_ID", "appid-cancelled-partial-refund"
    )

    result = await _service(db).reconcile_pay_from_query(
        {
            "out_trade_no": "order-cancelled-partial-refund",
            "mchid": "mch-cancelled-partial-refund",
            "appid": "appid-cancelled-partial-refund",
            "trade_state": "SUCCESS",
            "amount": {"total": 17800, "currency": "CNY"},
            "transaction_id": "wx-cancelled-partial-refund",
            "success_time": "2026-09-25T12:00:00+08:00",
        }
    )

    assert result["paymentStatus"] == "paid"
    latest = await order_repo.get_order("order-cancelled-partial-refund")
    assert latest is not None
    payment = loads_payment(latest.payment)
    assert payment["status"] == "paid"
    assert payment["refundStatus"] == "partial"
    assert payment["refundFen"] == 8000
    assert payment["transactionId"] == "wx-cancelled-partial-refund"
