"""券支付联动测试：快照、核销、退回、取消清快照、支付路径金额。"""

import aiosqlite
import pytest

from app.config import settings
from app.models.coupon import CouponTemplate, CouponType
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.config_repo import ConfigRepo
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.coupon import CouponService
from app.service.coupon.inventory import CouponInventoryService
from app.service.order import OrderApplicationService
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
)
from app.service.order.payment_state import dumps_payment, loads_payment, now_text

MOBILE = "13800000004"
OPENID = "openid_m4_coupon_001"
USER_ID = f"wx_{OPENID}"


async def _seed_member(db: aiosqlite.Connection) -> None:
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '券支付测试', 'high', 1)",
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
        "INSERT INTO member_balance (mobile, points) VALUES (?, 0)", (MOBILE,)
    )
    await db.commit()


async def _seed_coupon(db: aiosqlite.Connection, coupon_id: str = "c1") -> None:
    repo = CouponInventoryRepo(db)
    await repo.insert(
        CouponInventoryEntry(
            coupon_id=coupon_id,
            status=CouponStatus.TAKE,
            mobile=MOBILE,
            coupon_group_id="cg_001",
            title="满30减5",
            value_fen=500,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id="cg_001",
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )


async def _seed_template(db: aiosqlite.Connection) -> None:
    await CouponTemplateRepo(db).upsert_from_youzan(
        CouponTemplate(
            id="cg_001",
            name="满30减5",
            coupon_type=CouponType.FULL_REDUCTION,
            threshold_fen=3000,
            value_fen=500,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )


@pytest.fixture
def coupon_service(db: aiosqlite.Connection) -> CouponService:
    return CouponService(
        template_repo=CouponTemplateRepo(db),
        inventory_repo=CouponInventoryRepo(db),
        customer_repo=CustomerMasterRepo(db),
        order_repo=OrderRepo(db),
        inventory_service=CouponInventoryService(db),
    )


@pytest.fixture
def order_service(db: aiosqlite.Connection) -> OrderApplicationService:
    return OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )


async def _create_order(
    order_service: OrderApplicationService, price_fen: int = 10_000
) -> str:
    created = await order_service.create_order(
        {
            "items": [
                {
                    "productId": "p_m4_coupon_001",
                    "title": "M4 券支付蛋糕",
                    "priceFen": price_fen,
                    "quantity": 1,
                }
            ],
            "receiverName": "券支付测试",
            "receiverPhone": MOBILE,
            "receiverAddress": "测试地址",
            "deliveryType": "delivery",
            "deliveryAddress": "测试地址",
            "expectTime": "2026-08-20 19:00",
            "userOpenid": OPENID,
            "remark": "",
        },
        user_id=USER_ID,
    )
    return created["orderId"]


def test_coupon_service_bare_construction_deferred() -> None:
    """无参构造不得急切访问 _db（lifespan 装配无 db_session_scope 的回归）。"""
    service = CouponService()
    assert service._inventory_service is None


@pytest.mark.asyncio
async def test_coupon_service_lazy_inventory_resolves(db) -> None:
    """惰性券库存服务在方法调用期按 order_repo 数据源构建。"""
    service = CouponService(order_repo=OrderRepo(db))
    inventory = service._inventory
    assert inventory is not None


@pytest.mark.asyncio
async def test_apply_coupon_snapshot(db, coupon_service, order_service) -> None:
    """应用券写快照（couponFen/couponId），remain 正确。"""
    await _seed_member(db)
    await _seed_template(db)
    await _seed_coupon(db)
    order_id = await _create_order(order_service)
    result = await coupon_service.apply_coupon(
        order_id, user_id=USER_ID, coupon_id="c1"
    )
    assert result["couponFen"] == 500
    assert result["remainFen"] == 9500
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    assert payment.get("couponId") == "c1"
    assert payment.get("couponFen") == 500


@pytest.mark.asyncio
async def test_apply_coupon_rejected_when_paid(
    db, coupon_service, order_service
) -> None:
    """已支付订单不可再应用券。"""
    await _seed_member(db)
    await _seed_template(db)
    await _seed_coupon(db)
    order_id = await _create_order(order_service)
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    payment["status"] = "paid"
    await OrderRepo(db).update_payment(order_id, dumps_payment(payment), now_text())
    await OrderRepo(db)._db.commit()
    with pytest.raises(ValueError):
        await coupon_service.apply_coupon(order_id, user_id=USER_ID, coupon_id="c1")


@pytest.mark.asyncio
async def test_consume_on_payment(db, coupon_service, order_service) -> None:
    """支付成功后核销券，重复调用幂等。"""
    await _seed_member(db)
    await _seed_template(db)
    await _seed_coupon(db)
    order_id = await _create_order(order_service)
    await coupon_service.apply_coupon(order_id, user_id=USER_ID, coupon_id="c1")
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    payment["status"] = "paid"
    await OrderRepo(db).update_payment(order_id, dumps_payment(payment), now_text())
    await OrderRepo(db)._db.commit()
    updated = await OrderRepo(db).get_order(order_id)
    assert updated is not None
    await coupon_service.consume_on_payment(updated)
    await coupon_service.consume_on_payment(updated)
    rows = await db.execute_fetchall(
        "SELECT id FROM coupon_inventory WHERE coupon_id = 'c1' AND status = 'CONSUME' AND source = 'order'"
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_balance_pay_paid_retry_consumes_coupon(
    db, coupon_service, order_service
) -> None:
    """余额支付置 paid 与核销之间崩溃，重试走 PAID 分支应补核销且幂等。"""
    await _seed_member(db)
    await _seed_template(db)
    await _seed_coupon(db)
    order_id = await _create_order(order_service)
    await coupon_service.apply_coupon(order_id, user_id=USER_ID, coupon_id="c1")
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    payment["status"] = "paid"
    payment["method"] = "balance"
    payment["balanceFen"] = 9500
    await OrderRepo(db).update_payment(order_id, dumps_payment(payment), now_text())
    await OrderRepo(db)._db.commit()
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    svc = StoredValueOrderPaymentService(
        order_repo=OrderRepo(db), member_service=member_service
    )
    result = await svc.pay_order_with_balance(order_id, user_id=USER_ID)
    assert result["paymentStatus"] == "paid"
    rows = await db.execute_fetchall(
        "SELECT id FROM coupon_inventory WHERE coupon_id = 'c1' AND status = 'CONSUME' AND source = 'order'"
    )
    assert len(rows) == 1
    await svc.pay_order_with_balance(order_id, user_id=USER_ID)
    rows = await db.execute_fetchall(
        "SELECT id FROM coupon_inventory WHERE coupon_id = 'c1' AND status = 'CONSUME' AND source = 'order'"
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_clear_snapshot_on_unpaid_cancel(
    db, coupon_service, order_service
) -> None:
    """未支付取消只清快照，不写 BACK 行。"""
    await _seed_member(db)
    await _seed_template(db)
    await _seed_coupon(db)
    order_id = await _create_order(order_service)
    await coupon_service.apply_coupon(order_id, user_id=USER_ID, coupon_id="c1")
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    await coupon_service.clear_applied(order)
    latest = await CouponInventoryRepo(db).get_latest_state(
        "c1", MOBILE, authority=settings.COUPON_AUTHORITY
    )
    assert latest is not None
    assert latest["status"] == CouponStatus.TAKE
    rows = await db.execute_fetchall(
        "SELECT id FROM coupon_inventory WHERE status IN ('CONSUME', 'BACK') AND source = 'order'"
    )
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_refund_coupon_after_paid_refund(
    db, coupon_service, order_service
) -> None:
    """已支付全单退款退回券（BACK 行），重复调用幂等。"""
    await _seed_member(db)
    await _seed_template(db)
    await _seed_coupon(db)
    order_id = await _create_order(order_service)
    await coupon_service.apply_coupon(order_id, user_id=USER_ID, coupon_id="c1")
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    payment["status"] = "paid"
    await OrderRepo(db).update_payment(order_id, dumps_payment(payment), now_text())
    await OrderRepo(db)._db.commit()
    updated = await OrderRepo(db).get_order(order_id)
    assert updated is not None
    await coupon_service.consume_on_payment(updated)
    await coupon_service.refund_coupon(updated)
    await coupon_service.refund_coupon(updated)
    rows = await db.execute_fetchall(
        "SELECT id FROM coupon_inventory WHERE coupon_id = 'c1' AND status = 'BACK' AND source = 'order'"
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_get_my_coupons(db, coupon_service, order_service) -> None:
    """我的券列表按最新态返回。"""
    await _seed_member(db)
    await _seed_template(db)
    await _seed_coupon(db)
    result = await coupon_service.get_my_coupons(USER_ID)
    assert result["mobile"] == MOBILE
    assert len(result["coupons"]) == 1
    assert result["coupons"][0]["couponId"] == "c1"
    assert result["coupons"][0]["status"] == CouponStatus.TAKE


@pytest.mark.asyncio
async def test_redeem_preview(db, coupon_service, order_service) -> None:
    """选券预览返回可用券与可减金额。"""
    await _seed_member(db)
    await _seed_template(db)
    await _seed_coupon(db)
    order_id = await _create_order(order_service)
    result = await coupon_service.redeem_preview(order_id, user_id=USER_ID)
    assert len(result["available"]) == 1
    assert result["available"][0]["couponId"] == "c1"
    assert result["available"][0]["discountFen"] == 500


@pytest.mark.asyncio
async def test_balance_pay_full_covered_by_coupon(
    db, coupon_service, order_service
) -> None:
    """券全额抵扣：余额支付按 0 金额扣减直接置 paid 并核销券。"""
    await _seed_member(db)
    await CouponTemplateRepo(db).upsert_from_youzan(
        CouponTemplate(
            id="cg_nt",
            name="无门槛10元券",
            coupon_type=CouponType.NO_THRESHOLD,
            threshold_fen=0,
            value_fen=10_000,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await CouponInventoryRepo(db).insert(
        CouponInventoryEntry(
            coupon_id="c2",
            status=CouponStatus.TAKE,
            mobile=MOBILE,
            coupon_group_id="cg_nt",
            title="无门槛10元券",
            value_fen=10_000,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id="cg_nt",
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    order_id = await _create_order(order_service, price_fen=10_000)
    await coupon_service.apply_coupon(order_id, user_id=USER_ID, coupon_id="c2")
    from app.service.stored_value.member import MemberBalanceService
    from app.service.stored_value.payment import StoredValueOrderPaymentService

    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    service = StoredValueOrderPaymentService(
        order_repo=OrderRepo(db),
        member_service=member_service,
    )
    result = await service.pay_order_with_balance(order_id, user_id=USER_ID)
    assert result["paymentStatus"] == "paid"
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    assert payment.get("couponFen") == 10_000
    assert payment.get("balanceFen") == 0
    rows = await db.execute_fetchall(
        "SELECT id FROM coupon_inventory WHERE coupon_id = 'c2' AND status = 'CONSUME'"
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_balance_pay_remainder_after_coupon(
    db, coupon_service, order_service
) -> None:
    """应用券后余额支付剩余部分（partial 守卫放宽，paid 快照保留券字段）。"""
    await _seed_member(db)
    await _seed_template(db)
    await _seed_coupon(db)
    await MemberBalanceRepo(db).credit_stored_value(MOBILE, 10_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await coupon_service.apply_coupon(order_id, user_id=USER_ID, coupon_id="c1")
    from app.service.stored_value.member import MemberBalanceService
    from app.service.stored_value.payment import StoredValueOrderPaymentService

    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    service = StoredValueOrderPaymentService(
        order_repo=OrderRepo(db),
        member_service=member_service,
    )
    result = await service.pay_order_with_balance(order_id, user_id=USER_ID)
    assert result["paymentStatus"] == "paid"
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    assert payment.get("couponFen") == 500
    assert payment.get("balanceFen") == 9500
    rows = await db.execute_fetchall(
        "SELECT id FROM coupon_inventory WHERE coupon_id = 'c1' AND status = 'CONSUME'"
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_apply_coupon_then_points_keeps_both(
    db, coupon_service, order_service, monkeypatch
) -> None:
    """先券后积分：积分快照合并保留券字段，remain 正确（顺序不敏感）。

    B3.4 围栏下积分抵扣写入口默认关闭，本测试放开围栏验证 D1 放开后的
    快照合并语义（围栏本身由 test_points_payment.py 覆盖）。
    """
    monkeypatch.setattr("app.service.points.payment.POINTS_DEDUCTION_FENCE", False)
    await _seed_member(db)
    await _seed_template(db)
    await _seed_coupon(db)
    await MemberBalanceRepo(db).credit_points(MOBILE, 100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await coupon_service.apply_coupon(order_id, user_id=USER_ID, coupon_id="c1")
    from app.repository.customer_master_repo import CustomerMasterRepo
    from app.repository.points_ledger_repo import PointsLedgerRepo
    from app.service.points import PointsService

    points_service = PointsService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=PointsLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
        order_repo=OrderRepo(db),
    )
    result = await points_service.apply_points(order_id, user_id=USER_ID)
    assert result["pointsFen"] == 5000
    assert result["remainFen"] == 4500
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    assert payment.get("couponId") == "c1"
    assert payment.get("couponFen") == 500
    assert payment.get("pointsFen") == 5000


@pytest.mark.asyncio
async def test_apply_coupon_rejected_when_balance_partial_paid(
    db, coupon_service, order_service
) -> None:
    """余额部分已扣（真实 partial）后禁止再应用券。"""
    await _seed_member(db)
    await _seed_template(db)
    await _seed_coupon(db)
    await MemberBalanceRepo(db).credit_stored_value(MOBILE, 10_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    from app.service.stored_value.member import MemberBalanceService
    from app.service.stored_value.payment import StoredValueOrderPaymentService

    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    service = StoredValueOrderPaymentService(
        order_repo=OrderRepo(db),
        member_service=member_service,
    )
    combined = await service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=3000
    )
    assert combined["payment"]["status"] == "partial"
    with pytest.raises(ValueError):
        await coupon_service.apply_coupon(order_id, user_id=USER_ID, coupon_id="c1")


@pytest.mark.asyncio
async def test_redeem_preview_empty_when_balance_partial_paid(
    db, coupon_service, order_service
) -> None:
    """余额已扣的真实 partial 上选券预览返回空可用券（与 apply 守卫一致）。"""
    await _seed_member(db)
    await _seed_template(db)
    await _seed_coupon(db)
    await MemberBalanceRepo(db).credit_stored_value(MOBILE, 10_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    from app.service.stored_value.member import MemberBalanceService
    from app.service.stored_value.payment import StoredValueOrderPaymentService

    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    service = StoredValueOrderPaymentService(
        order_repo=OrderRepo(db),
        member_service=member_service,
    )
    await service.prepare_combined_payment(order_id, user_id=USER_ID, balance_fen=3000)
    result = await coupon_service.redeem_preview(order_id, user_id=USER_ID)
    assert result["available"] == []


@pytest.mark.asyncio
async def test_coupon_consumed_then_points_fail_rolls_back_all(
    db: aiosqlite.Connection,
    coupon_service,
    order_service,
) -> None:
    """B3.5（评审问题 1）：券核销成功 + 积分扣减失败 → 外层事务整体回滚。

    复现评审描述：修复前仓储自提交导致「券已 CONSUME、订单已 paid、积分流水为空」；
    修复后统一支付应用服务独占事务，券与积分任一失败全部资产回滚。
    """
    await _seed_member(db)  # points = 0，积分扣减必然失败
    await _seed_template(db)
    await _seed_coupon(db)
    order_id = await _create_order(order_service, price_fen=10_000)
    await coupon_service.apply_coupon(order_id, user_id=USER_ID, coupon_id="c1")
    # 直写积分抵扣 partial（绕过 B3.4 围栏，聚焦结算链路整体回滚）
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    payment["status"] = "partial"
    payment["method"] = "combined"
    payment["pointsUsed"] = 5000
    payment["pointsFen"] = 5000
    payment["remainFen"] = 4500
    await OrderRepo(db).update_payment(order_id, dumps_payment(payment), now_text())
    await OrderRepo(db)._db.commit()
    with pytest.raises(ValueError, match="积分余额不足"):
        await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    # 整体回滚：订单未支付、券未核销、无积分流水
    order_latest = await OrderRepo(db).get_order(order_id)
    assert order_latest is not None
    assert str(loads_payment(order_latest.payment).get("status")) == "partial"
    rows = await db.execute_fetchall(
        "SELECT status FROM coupon_inventory WHERE coupon_id = 'c1' ORDER BY id DESC LIMIT 1"
    )
    assert rows and rows[0]["status"] == "TAKE"
    ledger = await db.execute_fetchall(
        "SELECT COUNT(*) AS c FROM points_ledger WHERE mobile = ?", (MOBILE,)
    )
    assert int(ledger[0]["c"]) == 0
