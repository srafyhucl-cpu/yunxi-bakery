"""微信退款通知闭环测试：事实、补偿、案件、累计同一事务。"""

import json

import aiosqlite
import pytest

from app.models.order import Order, OrderStatus
from app.repository.config_repo import ConfigRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_repo import OrderRepo
from app.repository.points_refund_reconcile_repo import PointsRefundReconcileRepo
from app.repository.session_repo import SessionRepo
from app.repository.wechat_refund_event_repo import WechatRefundEventRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order import OrderApplicationService
from app.service.order.payment_state import loads_payment

MOBILE = "13800009000"
OPENID = "openid_refund_001"
USER_ID = f"wx_{OPENID}"


def _service(db: aiosqlite.Connection) -> OrderApplicationService:
    """构造订单应用服务，仓库直连用例数据库。"""
    return OrderApplicationService(
        order_repo=OrderRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )


async def _seed_member(db: aiosqlite.Connection) -> None:
    """seeding 会员身份与余额行。"""
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '退款测试', 'high', 1)",
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
        "VALUES (?, 0, 0)",
        (MOBILE,),
    )
    await db.commit()


def _paid_payment(
    balance_fen: int = 0, transaction_id: str = "4200000000202606170000000001"
) -> str:
    """构造已支付快照，腿为空或仅余额。"""
    return json.dumps(
        {
            "status": "paid",
            "method": "wechat",
            "paidAt": "2026-06-17 12:00:00",
            "transactionId": transaction_id,
            "couponFen": 0,
            "balanceFen": balance_fen,
            "pointsFen": 0,
            "pointsUsed": 0,
            "pointsAwarded": 0,
        }
    )


async def _seed_paid_order(
    db: aiosqlite.Connection,
    order_id: str,
    total_yuan: float,
    balance_fen: int = 0,
) -> None:
    """直写已支付订单。"""
    await db.execute(
        "INSERT OR IGNORE INTO sessions (id, channel, user_id, status) "
        "VALUES (?, ?, ?, ?)",
        ("session-1", "miniapp", USER_ID, "active"),
    )
    await OrderRepo(db).create_order(
        Order(
            id=order_id,
            session_id="session-1",
            channel="miniapp",
            user_id=USER_ID,
            products="[]",
            total_amount=total_yuan,
            delivery="{}",
            payment=_paid_payment(balance_fen),
            status=OrderStatus.PENDING,
            remark="",
            created_at="2026-06-17 11:00:00",
            updated_at="2026-06-17 12:00:00",
        )
    )
    await db.commit()


def _refund_notify(
    order_id: str,
    out_refund_no: str,
    refund_fen: int,
    payer_refund_fen: int,
    payer_total_fen: int = 19800,
) -> dict:
    """构造已解密的退款成功事务体。"""
    return {
        "mchid": "mch-test",
        "out_trade_no": order_id,
        "transaction_id": "4200000000202606170000000001",
        "out_refund_no": out_refund_no,
        "refund_id": f"wx-{out_refund_no}",
        "refund_status": "SUCCESS",
        "success_time": "2026-06-17T13:00:00+08:00",
        "amount": {
            "total": 19800,
            "refund": refund_fen,
            "payer_total": payer_total_fen,
            "payer_refund": payer_refund_fen,
        },
    }


async def _patch_mch(monkeypatch: pytest.MonkeyPatch) -> None:
    """固定商户号配置。"""
    monkeypatch.setattr(
        "app.service.order.refund_notification.settings.WECHAT_PAY_MCH_ID", "mch-test"
    )


@pytest.mark.asyncio
async def test_full_refund_end_to_end_with_balance_leg(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """全额退款端到端：事实、余额腿、累计一次落账。"""
    await _seed_member(db)
    await _seed_paid_order(db, "order-ref-1", 198.00, balance_fen=2000)
    await _patch_mch(monkeypatch)
    service = _service(db)
    notify = _refund_notify("order-ref-1", "R1", 17800, 17800)
    result = await service.reconcile_refund_from_query(
        notify, payer_total_fen=19800 - 2000
    )
    assert result["accumulatedFen"] == 19800 - 2000
    balance = await MemberBalanceRepo(db).get_stored_value_fen(MOBILE)
    assert balance == 2000
    event = await WechatRefundEventRepo(db).get_by_out_refund_no("R1")
    assert event is not None
    assert int(event["payer_refund_fen"]) == 19800 - 2000
    order = await OrderRepo(db).get_order("order-ref-1")
    assert order is not None
    payment = loads_payment(order.payment)
    assert payment["refundStatus"] == "full"

    duplicate = await service.reconcile_refund_from_query(
        notify, payer_total_fen=19800 - 2000
    )
    assert duplicate.get("duplicate") is True
    assert await MemberBalanceRepo(db).get_stored_value_fen(MOBILE) == 2000
    events = await db.execute_fetchall(
        "SELECT out_refund_no FROM wechat_refund_events WHERE order_id = ?",
        ("order-ref-1",),
    )
    assert len(events) == 1


@pytest.mark.asyncio
async def test_partial_refund_records_fact_and_case_without_legs(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """部分退款记录事实与累计并建案，腿转人工。"""
    await _seed_member(db)
    await _seed_paid_order(db, "order-ref-2", 198.00)
    await _patch_mch(monkeypatch)
    service = _service(db)
    result = await service.reconcile_refund_from_query(
        _refund_notify("order-ref-2", "R2", 8000, 8000), payer_total_fen=19800
    )
    assert result["accumulatedFen"] == 8000
    order = await OrderRepo(db).get_order("order-ref-2")
    assert order is not None
    assert loads_payment(order.payment)["refundStatus"] == "partial"
    cases = await PointsRefundReconcileRepo(db).list_open()
    assert [row["unique_id"] for row in cases] == ["refund:partial:R2"]


@pytest.mark.asyncio
async def test_over_refund_rejected_with_case_preserved(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """超额退款拒绝并保留案件，不写累计。"""
    await _seed_member(db)
    await _seed_paid_order(db, "order-ref-3", 198.00)
    await _patch_mch(monkeypatch)
    service = _service(db)
    first = await service.reconcile_refund_from_query(
        _refund_notify("order-ref-3", "R3a", 15000, 15000), payer_total_fen=19800
    )
    assert first["accumulatedFen"] == 15000
    second = await service.reconcile_refund_from_query(
        _refund_notify("order-ref-3", "R3b", 8000, 8000), payer_total_fen=19800
    )
    assert "rejected" in second
    order = await OrderRepo(db).get_order("order-ref-3")
    assert order is not None
    assert loads_payment(order.payment)["refundFen"] == 23000
    assert loads_payment(order.payment)["refundStatus"] == "over"
    cases = await PointsRefundReconcileRepo(db).list_open()
    reasons = sorted(row["unique_id"] for row in cases)
    assert "refund:over_refund:R3b" in reasons


@pytest.mark.asyncio
async def test_payer_total_mismatch_rejected_with_case(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """实付不一致拒绝并建案，不执行补偿。"""
    await _seed_member(db)
    await _seed_paid_order(db, "order-ref-4", 198.00)
    await _patch_mch(monkeypatch)
    service = _service(db)
    result = await service.reconcile_refund_from_query(
        _refund_notify("order-ref-4", "R4", 19800, 19800), payer_total_fen=100
    )
    assert "rejected" in result
    cases = await PointsRefundReconcileRepo(db).list_open()
    assert [row["unique_id"] for row in cases] == ["refund:payer_total_mismatch:R4"]
    events = await db.execute_fetchall(
        "SELECT out_refund_no FROM wechat_refund_events WHERE order_id = ?",
        ("order-ref-4",),
    )
    assert events == []


@pytest.mark.asyncio
async def test_refund_notify_rejects_wrong_mchid(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """商户号不匹配直接拒绝，不落事实。"""
    await _seed_paid_order(db, "order-ref-5", 198.00)
    service = _service(db)
    notify = _refund_notify("order-ref-5", "R5", 19800, 19800)
    notify["mchid"] = "mch-evil"
    with pytest.raises(ValueError, match="商户号"):
        await service.reconcile_refund_from_query(notify, payer_total_fen=19800)
    events = await db.execute_fetchall(
        "SELECT out_refund_no FROM wechat_refund_events WHERE order_id = ?",
        ("order-ref-5",),
    )
    assert events == []


@pytest.mark.asyncio
async def test_notify_then_query_share_single_fact(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """通知先到、查询后到，共用幂等键只落账一次。"""
    await _seed_member(db)
    await _seed_paid_order(db, "order-ref-6", 198.00)
    await _patch_mch(monkeypatch)
    service = _service(db)
    transaction = _refund_notify("order-ref-6", "R6", 19800, 19800)
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
    raw_body = json.dumps({"id": "EV-R6", "resource": {}}).encode("utf-8")
    first = await service.handle_wechat_refund_notify(raw_body=raw_body, headers={})
    assert first["accumulatedFen"] == 19800
    second = await service.handle_wechat_refund_notify(raw_body=raw_body, headers={})
    assert second.get("duplicate") is True
    third = await service.reconcile_refund_from_query(
        transaction, payer_total_fen=19800
    )
    assert third.get("duplicate") is True
    events = await db.execute_fetchall(
        "SELECT out_refund_no FROM wechat_refund_events WHERE order_id = ?",
        ("order-ref-6",),
    )
    assert len(events) == 1
    order = await OrderRepo(db).get_order("order-ref-6")
    assert order is not None
    assert loads_payment(order.payment)["refundStatus"] == "full"
