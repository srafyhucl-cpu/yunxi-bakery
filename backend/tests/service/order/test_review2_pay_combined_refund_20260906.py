"""复核第二轮 TDD 测试：组合支付原子性、退款金额合同、查询认领统一、指纹落库、失败租约一致。

每个测试先在本轮实现前失败，修复后通过；只断言真实运行行为。
"""

import json

import aiosqlite
import pytest

from app.config import settings
from app.models.order import Order, OrderStatus
from app.repository.config_repo import ConfigRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order import OrderApplicationService
from app.service.order.notify_intake import build_notify_key, claim_notify, fail_notify
from app.service.order.wechat_normalizers import (
    RefundNotifyNormalizer,
    WechatProtocolError,
)

MOBILE = "13800007711"
OPENID = "openid_rev2_001"
USER_ID = f"wx_{OPENID}"


def _order_service(db: aiosqlite.Connection) -> OrderApplicationService:
    """构造订单应用服务，仓库直连用例数据库。"""
    return OrderApplicationService(
        order_repo=OrderRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )


async def _seed_member(db: aiosqlite.Connection, balance_fen: int) -> None:
    """落库会员身份与余额账户。"""
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '复核测试', 'high', 1)",
        (f"cm_{OPENID}", MOBILE),
    )
    await db.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (f"cil_{OPENID}", f"cm_{OPENID}", OPENID, OPENID),
    )
    await db.execute(
        "INSERT INTO member_balance (mobile, stored_value_fen, points) "
        "VALUES (?, ?, 0)",
        (MOBILE, balance_fen),
    )
    await db.commit()


async def _seed_unpaid_order(
    db: aiosqlite.Connection, order_id: str, total_yuan: float
) -> None:
    """直写未支付订单，聚焦组合支付链路。"""
    await db.execute(
        "INSERT OR IGNORE INTO sessions (id, channel, user_id, status) "
        "VALUES (?, ?, ?, ?)",
        ("session-rev2", "miniapp", USER_ID, "active"),
    )
    await OrderRepo(db).create_order(
        Order(
            id=order_id,
            session_id="session-rev2",
            channel="miniapp",
            user_id=USER_ID,
            products="[]",
            total_amount=total_yuan,
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
            created_at="2026-09-06 12:00:00",
            updated_at="2026-09-06 12:00:00",
        )
    )
    await db.commit()


def _refund_body(**overrides) -> dict:
    """构造退款通知解密体，默认全额合法。"""
    body = {
        "mchid": "mch-rev2",
        "out_trade_no": "order-rev2-a",
        "transaction_id": "4200000000202609060000000001",
        "out_refund_no": "refund-rev2-a",
        "refund_id": "wx-refund-rev2-a",
        "refund_status": "SUCCESS",
        "success_time": "2026-09-06T12:00:00+08:00",
        "amount": {
            "total": 1000,
            "refund": 1000,
            "payer_total": 1000,
            "payer_refund": 1000,
        },
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_p01_combined_prepay_failure_rolls_back(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0-1：剩余支付会话构造失败时扣款与订单状态整体回滚。"""
    from app.repository.balance_ledger_repo import BalanceLedgerRepo
    from app.repository.customer_master_repo import CustomerMasterRepo
    from app.service.stored_value import payment as payment_module
    from app.service.stored_value.member import MemberBalanceService
    from app.service.stored_value.payment import StoredValueOrderPaymentService

    await _seed_member(db, 10000)
    await _seed_unpaid_order(db, "order-rev2-comb", 100.00)

    async def _failing_session(self, order, remain_fen: int):
        raise RuntimeError("微信预下单失败")

    monkeypatch.setattr(
        payment_module.StoredValueOrderPaymentService,
        "_build_remainder_session",
        _failing_session,
    )
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    pay_service = StoredValueOrderPaymentService(
        order_repo=OrderRepo(db), member_service=member_service
    )
    with pytest.raises(RuntimeError, match="微信预下单失败"):
        await pay_service.prepare_combined_payment(
            "order-rev2-comb", user_id=USER_ID, balance_fen=2000
        )
    assert await MemberBalanceRepo(db).get_stored_value_fen(MOBILE) == 10000
    order = await OrderRepo(db).get_order("order-rev2-comb")
    assert order is not None
    assert json.loads(order.payment)["status"] == "unpaid"
    assert int(json.loads(order.payment).get("balanceFen", 0)) == 0


@pytest.mark.asyncio
async def test_p02_refund_amount_contract_rejected() -> None:
    """P0-2：金额关系非法（负数/超额/ payer 越界/缺交易号）报文直接拒绝。"""
    normalizer = RefundNotifyNormalizer()
    base = _refund_body()
    assert normalizer.normalize(base).refund_fen == 1000
    bad_amounts = [
        {"total": -1, "refund": 1000, "payer_total": 1000, "payer_refund": 1000},
        {"total": 1000, "refund": 1001, "payer_total": 1000, "payer_refund": 1000},
        {"total": 1000, "refund": 1000, "payer_total": 1000, "payer_refund": 1001},
        {"total": 1000, "refund": 500, "payer_total": 1000, "payer_refund": 600},
    ]
    for amount in bad_amounts:
        with pytest.raises(WechatProtocolError):
            normalizer.normalize(_refund_body(amount=amount))
    body = _refund_body()
    del body["transaction_id"]
    with pytest.raises(WechatProtocolError):
        normalizer.normalize(body)


@pytest.mark.asyncio
async def test_p02_total_mismatch_recorded_with_case(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0-2：通知原金额与订单总额不一致时建案确认，不入账不补偿。"""
    from app.service.order.refund_notification import WechatRefundNotificationService
    from app.service.order.wechat_normalizers import RefundNotify

    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-rev2")
    await db.execute(
        "INSERT OR IGNORE INTO sessions (id, channel, user_id, status) "
        "VALUES (?, ?, ?, ?)",
        ("session-rev2", "miniapp", USER_ID, "active"),
    )
    await OrderRepo(db).create_order(
        Order(
            id="order-rev2-a",
            session_id="session-rev2",
            channel="miniapp",
            user_id=USER_ID,
            products="[]",
            total_amount=10.00,
            delivery="{}",
            payment=json.dumps(
                {
                    "status": "paid",
                    "method": "wechat",
                    "paidAt": "2026-09-06 12:00:00",
                    "transactionId": "4200000000202609060000000001",
                    "couponFen": 0,
                    "balanceFen": 0,
                    "pointsFen": 0,
                }
            ),
            status=OrderStatus.PENDING,
            remark="",
            created_at="2026-09-06 12:00:00",
            updated_at="2026-09-06 12:00:00",
        )
    )
    await db.commit()
    notify = RefundNotify(
        mchid="mch-rev2",
        out_trade_no="order-rev2-a",
        transaction_id="4200000000202609060000000001",
        out_refund_no="refund-rev2-total",
        refund_id="wx-total",
        refund_status="SUCCESS",
        success_time="2026-09-06T12:00:00+08:00",
        total_fen=999,
        refund_fen=999,
        payer_total_fen=1000,
        payer_refund_fen=999,
        user_received_account="",
    )
    result = await WechatRefundNotificationService(OrderRepo(db)).apply_refund_notify(
        notify
    )
    assert result.get("kind") == "rejected_recorded"
    events = await db.execute_fetchall(
        "SELECT out_refund_no FROM wechat_refund_events WHERE out_refund_no = ?",
        ("refund-rev2-total",),
    )
    assert events == []


@pytest.mark.asyncio
async def test_corr1_query_recovery_uses_claim_machine(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """修正 1：查询恢复统一走认领状态机，重复恢复直接确认。"""
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-rev2")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-rev2")
    await _seed_unpaid_order(db, "order-rev2-q", 10.00)
    service = _order_service(db)
    query = {
        "out_trade_no": "order-rev2-q",
        "transaction_id": "4200000000202609060000000009",
        "trade_state": "SUCCESS",
        "mchid": "mch-rev2",
        "appid": "appid-rev2",
        "amount": {"total": 1000, "currency": "CNY"},
        "success_time": "2026-09-06T12:00:00+08:00",
    }
    first = await service.reconcile_pay_from_query(query)
    assert first["paymentStatus"] == "paid"
    second = await service.reconcile_pay_from_query(query)
    assert second["paymentStatus"] == "paid"
    rows = await db.execute_fetchall(
        "SELECT status, attempt_count FROM inbox_events WHERE message_key = ?",
        ("wechat_pay_notify:query:pay:order-rev2-q:4200000000202609060000000009",),
    )
    assert len(rows) == 1
    assert str(rows[0]["status"]) == "processed"


@pytest.mark.asyncio
async def test_corr2_fingerprint_written_at_insert(db: aiosqlite.Connection) -> None:
    """修正 2：正式流水指纹在插入时落库，不存在先空后补窗口。"""
    from app.repository.balance_ledger_repo import BalanceLedgerRepo
    from app.repository.member_balance_repo import MemberBalanceRepo
    from app.service.stored_value.member import MemberBalanceService

    await db.execute(
        "INSERT INTO member_balance (mobile, stored_value_fen, points) "
        "VALUES (?, 0, 0)",
        (MOBILE,),
    )
    await db.commit()
    service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
    )
    from app.database import db_conn_var
    from app.repository.base import DatabaseHandle

    handle = DatabaseHandle(db)
    token = db_conn_var.set(handle)
    try:
        await service.credit(
            user_id="u-rev2",
            mobile=MOBILE,
            amount_fen=100,
            biz_type="recharge",
            biz_id="b-rev2",
            unique_id="sv-rev2-fp",
            source="recharge",
        )
        await db.commit()
    finally:
        db_conn_var.reset(token)
    rows = await db.execute_fetchall(
        "SELECT request_fingerprint FROM balance_ledger WHERE unique_id = ?",
        ("sv-rev2-fp",),
    )
    assert len(rows) == 1
    assert str(rows[0]["request_fingerprint"] or "") != ""


@pytest.mark.asyncio
async def test_p16_fail_respects_lease_expiry(db: aiosqlite.Connection) -> None:
    """P1-6：租约过期后陈旧 worker 的失败标记同样被拒绝。"""
    claimed = await claim_notify(db, "evt-rev2-lease", {"id": "evt-rev2-lease"})
    assert claimed["decision"] == "claimed"
    await db.execute(
        "UPDATE inbox_events SET lease_until = datetime('now', '-1 second') "
        "WHERE message_key = ?",
        (build_notify_key("evt-rev2-lease"),),
    )
    with pytest.raises(ValueError, match="认领已过期"):
        await fail_notify(db, "evt-rev2-lease", claimed["claim_token"], "迟到失败")
    await db.commit()
