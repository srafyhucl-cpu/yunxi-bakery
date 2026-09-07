"""复核第三轮 TDD 测试：组合支付并发快照一致性。

事务外生成的预支付会话金额必须与事务内重算一致，
否则回滚本次扣款并要求重新发起。
"""

import json

import aiosqlite
import pytest

from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_repo import OrderRepo
from app.models.order import Order, OrderStatus
from app.service.stored_value.member import MemberBalanceService
from app.service.stored_value.payment import StoredValueOrderPaymentService

MOBILE = "13800008811"
OPENID = "openid_rev3_001"
USER_ID = f"wx_{OPENID}"


async def _seed_member(db: aiosqlite.Connection) -> None:
    """落库会员身份与 10000 分余额账户。"""
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '复核三轮', 'high', 1)",
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
        "VALUES (?, 10000, 0)",
        (MOBILE,),
    )
    await db.commit()


async def _seed_unpaid_order(db: aiosqlite.Connection, order_id: str) -> None:
    """直写 100.00 元未支付订单。"""
    await db.execute(
        "INSERT OR IGNORE INTO sessions (id, channel, user_id, status) "
        "VALUES (?, ?, ?, ?)",
        ("session-rev3", "miniapp", USER_ID, "active"),
    )
    await OrderRepo(db).create_order(
        Order(
            id=order_id,
            session_id="session-rev3",
            channel="miniapp",
            user_id=USER_ID,
            products="[]",
            total_amount=100.00,
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


@pytest.mark.asyncio
async def test_p0_concurrent_coupon_change_aborts_combined_pay(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0：并发改券后事务内重算不一致必须回滚，不写旧快照。"""
    from app.service.stored_value import payment as payment_module

    await _seed_member(db)
    await _seed_unpaid_order(db, "order-rev3-comb")

    async def _session_with_concurrent_coupon(self, order, remain_fen: int):
        # 模拟并发：在会话已生成后、扣款提交前，券快照落地 500 分。
        current = await OrderRepo(self._order_repo._db).get_order(order.id)
        assert current is not None
        payment = json.loads(current.payment)
        payment["couponId"] = "coupon-concurrent"
        payment["couponFen"] = 500
        await OrderRepo(self._order_repo._db).update_payment(
            current.id, json.dumps(payment), "2026-09-06 12:00:01"
        )
        await self._order_repo._db.commit()
        return {"mode": "wechat", "stale": True}

    monkeypatch.setattr(
        payment_module.StoredValueOrderPaymentService,
        "_build_remainder_session",
        _session_with_concurrent_coupon,
    )
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    pay_service = StoredValueOrderPaymentService(
        order_repo=OrderRepo(db), member_service=member_service
    )
    with pytest.raises(ValueError, match="重新发起"):
        await pay_service.prepare_combined_payment(
            "order-rev3-comb", user_id=USER_ID, balance_fen=2000
        )
    assert await MemberBalanceRepo(db).get_stored_value_fen(MOBILE) == 10000
    order = await OrderRepo(db).get_order("order-rev3-comb")
    assert order is not None
    payment = json.loads(order.payment)
    assert int(payment.get("balanceFen", 0)) == 0
    assert payment.get("status") == "unpaid"
    assert int(payment.get("couponFen", 0)) == 500


@pytest.mark.asyncio
async def test_p0_combined_pay_retries_after_abort(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0：中止后以新快照重新发起可成功，微信预下单按订单号幂等复用。"""
    from app.service.stored_value import payment as payment_module

    await _seed_member(db)
    await _seed_unpaid_order(db, "order-rev3-retry")
    calls: list[int] = []

    async def _session_once(self, order, remain_fen: int):
        calls.append(int(remain_fen))
        if len(calls) == 1:
            current = await OrderRepo(self._order_repo._db).get_order(order.id)
            assert current is not None
            payment = json.loads(current.payment)
            payment["couponId"] = "coupon-concurrent"
            payment["couponFen"] = 500
            await OrderRepo(self._order_repo._db).update_payment(
                current.id, json.dumps(payment), "2026-09-06 12:00:01"
            )
            await self._order_repo._db.commit()
        return {"mode": "wechat", "orderId": order.id, "remainFen": int(remain_fen)}

    monkeypatch.setattr(
        payment_module.StoredValueOrderPaymentService,
        "_build_remainder_session",
        _session_once,
    )
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    pay_service = StoredValueOrderPaymentService(
        order_repo=OrderRepo(db), member_service=member_service
    )
    with pytest.raises(ValueError, match="重新发起"):
        await pay_service.prepare_combined_payment(
            "order-rev3-retry", user_id=USER_ID, balance_fen=2000
        )
    result = await pay_service.prepare_combined_payment(
        "order-rev3-retry", user_id=USER_ID, balance_fen=2000
    )
    assert result["payment"]["status"] == "partial"
    assert result["payment"]["balanceFen"] == 2000
    assert result["payment"]["remainFen"] == 7500
    assert await MemberBalanceRepo(db).get_stored_value_fen(MOBILE) == 8000
    assert calls[0] == 8000 and calls[1] == 7500


@pytest.mark.asyncio
async def test_p0_combined_pay_refuses_split_connections(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0：储值服务与订单仓储不在同一事务连接时拒绝扣款。"""
    from app.database import init_db
    from app.service.stored_value import payment as payment_module

    await _seed_member(db)
    await _seed_unpaid_order(db, "order-rev3-split")

    async def _ok_session(self, order, remain_fen: int):
        return {"mode": "wechat"}

    monkeypatch.setattr(
        payment_module.StoredValueOrderPaymentService,
        "_build_remainder_session",
        _ok_session,
    )
    other = await init_db(":memory:")
    try:
        foreign_service = MemberBalanceService(
            balance_repo=MemberBalanceRepo(other),
            ledger_repo=BalanceLedgerRepo(other),
            customer_repo=CustomerMasterRepo(other),
        )
        pay_service = StoredValueOrderPaymentService(
            order_repo=OrderRepo(db), member_service=foreign_service
        )
        with pytest.raises(ValueError, match="同一事务连接"):
            await pay_service.prepare_combined_payment(
                "order-rev3-split", user_id=USER_ID, balance_fen=2000
            )
    finally:
        await other.close()
    assert await MemberBalanceRepo(db).get_stored_value_fen(MOBILE) == 10000


@pytest.mark.asyncio
async def test_p0_deduct_ok_but_cas_fails_rolls_back(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0：扣款成功但订单 CAS 更新失败时整体回滚，无孤儿流水。"""
    from app.repository.order_repo import OrderRepo as OrderRepoModule
    from app.service.stored_value import payment as payment_module

    await _seed_member(db)
    await _seed_unpaid_order(db, "order-rev3-cas")

    async def _ok_session(self, order, remain_fen: int):
        return {"mode": "wechat"}

    async def _cas_always_conflict(self, *args, **kwargs):
        return None

    monkeypatch.setattr(
        payment_module.StoredValueOrderPaymentService,
        "_build_remainder_session",
        _ok_session,
    )
    monkeypatch.setattr(
        OrderRepoModule,
        "update_payment_to_partial_if_unpaid_or_partial_active",
        _cas_always_conflict,
    )
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    pay_service = StoredValueOrderPaymentService(
        order_repo=OrderRepo(db), member_service=member_service
    )
    with pytest.raises(ValueError, match="更新冲突"):
        await pay_service.prepare_combined_payment(
            "order-rev3-cas", user_id=USER_ID, balance_fen=2000
        )
    assert await MemberBalanceRepo(db).get_stored_value_fen(MOBILE) == 10000
    rows = await db.execute_fetchall(
        "SELECT unique_id FROM balance_ledger WHERE unique_id = ?",
        ("combined_pay:order-rev3-cas",),
    )
    assert rows == []
    order = await OrderRepo(db).get_order("order-rev3-cas")
    assert order is not None
    assert json.loads(order.payment)["status"] == "unpaid"
