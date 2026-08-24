"""积分支付联动测试：快照、发分、退款（B3.4 围栏与两命令分流）。"""

import aiosqlite
import pytest

from datetime import datetime, timedelta

from app.repository.config_repo import ConfigRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.points_ledger_repo import PointsLedgerRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order import OrderApplicationService
from app.service.order.payment_state import (
    PAYMENT_TIMEOUT_MINUTES,
    dumps_payment,
    loads_payment,
    now_text,
)
from app.service.points import PointsService
from app.service.points.payment import POINTS_DEDUCTION_FENCE

MOBILE = "13800000003"
MOBILE_ORIGINAL = "13800000004"
OPENID = "openid_m3_pay_001"
USER_ID = f"wx_{OPENID}"


async def _seed_member(db: aiosqlite.Connection, *, points: int = 0) -> None:
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '积分支付测试', 'high', 1)",
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
        "INSERT INTO member_balance (mobile, points) VALUES (?, ?)",
        (MOBILE, points),
    )
    await db.commit()


@pytest.fixture
def points_service(db: aiosqlite.Connection) -> PointsService:
    return PointsService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=PointsLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
        order_repo=OrderRepo(db),
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
                    "productId": "p_m3_pay_001",
                    "title": "M3 支付联动蛋糕",
                    "priceFen": price_fen,
                    "quantity": 1,
                }
            ],
            "receiverName": "积分支付测试",
            "receiverPhone": MOBILE,
            "deliveryType": "delivery",
            "deliveryAddress": "积分支付测试地址",
            "expectTime": "2026-08-20 19:00",
        },
        user_id=USER_ID,
    )
    return created["orderId"]


async def _points(db: aiosqlite.Connection) -> int:
    rows = await db.execute_fetchall(
        "SELECT points FROM member_balance WHERE mobile = ? LIMIT 1", (MOBILE,)
    )
    return int(rows[0]["points"]) if rows else 0


async def _ledger_count(db: aiosqlite.Connection) -> int:
    rows = await db.execute_fetchall(
        "SELECT COUNT(*) AS c FROM points_ledger WHERE mobile = ?", (MOBILE,)
    )
    return int(rows[0]["c"])


async def _seed_points_partial(
    db: aiosqlite.Connection,
    order_id: str,
    *,
    points_used: int,
    points_fen: int,
    points_awarded: int | None = None,
    settled: bool = False,
) -> None:
    """直写积分抵扣 partial 快照（绕过 B3.4 围栏，测试两命令与结算路径）。"""
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    payment.update(
        {
            "status": "partial",
            "method": "combined",
            "pointsUsed": points_used,
            "pointsFen": points_fen,
            "remainFen": max(0, 10_000 - points_fen),
        }
    )
    if points_awarded is not None:
        payment["pointsAwarded"] = points_awarded
    if settled:
        payment["pointsSettledAt"] = now_text()
    await OrderRepo(db).update_payment(order_id, dumps_payment(payment), now_text())
    await db.commit()


@pytest.mark.asyncio
async def test_apply_points_fence_rejects_new_deduction(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """B3.4 围栏：积分抵扣写入口关闭，apply 直接拒绝且不动积分账。"""
    assert POINTS_DEDUCTION_FENCE is True
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    with pytest.raises(ValueError, match="积分抵扣已临时关闭"):
        await points_service.apply_points(order_id, user_id=USER_ID)
    order = await OrderRepo(db).get_order(order_id)
    payment = loads_payment(order.payment)
    assert str(payment.get("status")) == "unpaid"
    assert await _points(db) == 100_000
    assert await _ledger_count(db) == 0


@pytest.mark.asyncio
async def test_apply_points_rejects_repeat_and_preserves_created_at(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B3.4（评审问题 6）：围栏解除后只允许首次从未支付进入，重复应用被拒且保留首次创建时间。"""
    monkeypatch.setattr("app.service.points.payment.POINTS_DEDUCTION_FENCE", False)
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    order = await OrderRepo(db).get_order(order_id)
    original_created_at = loads_payment(order.payment)["createdAt"]
    result = await points_service.apply_points(order_id, user_id=USER_ID)
    assert result["paymentStatus"] == "partial"
    assert result["pointsFen"] == 5000
    assert result["remainFen"] == 5000
    # 首次应用保留原订单支付创建时间，不重写
    order_after = await OrderRepo(db).get_order(order_id)
    assert loads_payment(order_after.payment)["createdAt"] == original_created_at
    # 重复应用直接拒绝
    with pytest.raises(ValueError, match="不能重复应用"):
        await points_service.apply_points(order_id, user_id=USER_ID)
    order_final = await OrderRepo(db).get_order(order_id)
    assert loads_payment(order_final.payment)["createdAt"] == original_created_at


@pytest.mark.asyncio
async def test_two_orders_competing_points_balance_second_blocked(
    db: aiosqlite.Connection,
    order_service: OrderApplicationService,
) -> None:
    """B3.4（评审问题 1）：两订单竞争同一积分余额，扣减失败阻止第二单进入已支付。"""
    await _seed_member(db, points=5000)
    order_a = await _create_order(order_service, price_fen=10_000)
    order_b = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(db, order_a, points_used=5000, points_fen=5000)
    await _seed_points_partial(db, order_b, points_used=5000, points_fen=5000)
    # 第一单结算成功：扣减 5000 分、发分 50（余额 5000 - 5000 + 50 = 50）
    await order_service.confirm_mock_payment(order_a, user_id=USER_ID)
    assert await _points(db) == 50
    # 第二单余额不足：扣减失败必须阻止进入已支付，不得静默放行形成免费抵扣
    with pytest.raises(ValueError, match="积分余额不足"):
        await order_service.confirm_mock_payment(order_b, user_id=USER_ID)
    order_b_latest = await OrderRepo(db).get_order(order_b)
    payment_b = loads_payment(order_b_latest.payment)
    # 整体回滚：保持播种的 partial，绝不被标记为已支付
    assert str(payment_b.get("status")) == "partial"


@pytest.mark.asyncio
async def test_award_on_payment_after_mock_pay(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """mock 支付成功后发分并扣抵扣，重复确认幂等。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(db, order_id, points_used=5000, points_fen=5000)
    await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    assert await _points(db) == 95_050
    await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    assert await _points(db) == 95_050
    assert await _ledger_count(db) == 2


@pytest.mark.asyncio
async def test_refund_points_returns_used_and_claws_back_award(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """退款退回全部抵扣积分并收回全部已发积分，幂等。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(db, order_id, points_used=5000, points_fen=5000)
    await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    order = await OrderRepo(db).get_order(order_id)
    await points_service.refund_points(order)
    assert await _points(db) == 100_000
    await points_service.refund_points(order)
    assert await _points(db) == 100_000


async def test_apply_points_snapshot_with_coupon(
    order_service, db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """围栏解除后：券抵扣后积分抵扣上限随剩余应付收窄。"""
    monkeypatch.setattr("app.service.points.payment.POINTS_DEDUCTION_FENCE", False)
    from app.repository.member_balance_repo import MemberBalanceRepo
    from app.repository.points_ledger_repo import PointsLedgerRepo
    from app.repository.order_repo import OrderRepo
    from app.service.order.payment_state import dumps_payment, loads_payment, now_text
    from app.service.points import PointsService

    await _seed_member(db, points=10_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    points_service = PointsService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=PointsLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
        order_repo=OrderRepo(db),
    )
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    payment["couponFen"] = 8000
    payment["couponId"] = "c1"
    await OrderRepo(db).update_payment(order_id, dumps_payment(payment), now_text())
    await OrderRepo(db)._db.commit()

    result = await points_service.apply_points(order_id, user_id=USER_ID)
    assert result["pointsFen"] == 2000
    assert result["remainFen"] == 0
    persisted = await OrderRepo(db).get_order(order_id)
    assert persisted is not None
    snapshot = loads_payment(persisted.payment)
    assert snapshot.get("couponId") == "c1"
    assert snapshot.get("couponFen") == 8000


async def test_award_points_subtracts_coupon(
    order_service, db: aiosqlite.Connection
) -> None:
    """发分公式 total - coupon - balance - points。"""
    from app.repository.order_repo import OrderRepo
    from app.service.order.payment_state import dumps_payment, loads_payment, now_text
    from app.service.points.payment import PointsPaymentService

    await _seed_member(db, points=100)
    order_id = await _create_order(order_service, price_fen=10_000)
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    payment["couponFen"] = 3000
    payment["couponId"] = "c1"
    payment["status"] = "paid"
    await OrderRepo(db).update_payment(order_id, dumps_payment(payment), now_text())
    await OrderRepo(db)._db.commit()
    updated = await OrderRepo(db).get_order(order_id)
    assert updated is not None
    await PointsPaymentService(order_repo=OrderRepo(db)).award_on_payment(updated)
    rows = await db.execute_fetchall(
        "SELECT amount FROM points_ledger WHERE unique_id = ?",
        (f"points:award:{order_id}",),
    )
    # 实付 7000 分 -> 70 分
    assert rows and rows[0]["amount"] == 70


async def _reconcile_rows(db: aiosqlite.Connection, order_id: str) -> list[dict]:
    return await db.execute_fetchall(
        "SELECT order_id, reason, status, amount FROM points_refund_reconcile "
        "WHERE order_id = ? ORDER BY id ASC",
        (order_id,),
    )


@pytest.mark.asyncio
async def test_user_cancel_unsettled_releases_without_credit(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """未结算（从未支付）订单用户取消：只清快照，不凭空退回积分、不建对账案件。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(db, order_id, points_used=5000, points_fen=5000)
    await order_service.cancel_user_order(order_id, user_id=USER_ID)
    assert await _points(db) == 100_000
    credit_rows = await db.execute_fetchall(
        "SELECT COUNT(*) AS c FROM points_ledger WHERE mobile = ? AND amount > 0",
        (MOBILE,),
    )
    assert int(credit_rows[0]["c"]) == 0
    order = await OrderRepo(db).get_order(order_id)
    payment = loads_payment(order.payment)
    assert int(payment.get("pointsUsed", 0) or 0) == 0
    reconcile = await _reconcile_rows(db, order_id)
    assert reconcile == []


@pytest.mark.asyncio
async def test_admin_cancel_unsettled_releases_without_credit(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """后台取消未结算订单：只清快照，不凭空退回积分、不建对账案件。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(db, order_id, points_used=5000, points_fen=5000)
    await order_service.update_admin_order_status(order_id, "cancelled")
    assert await _points(db) == 100_000
    reconcile = await _reconcile_rows(db, order_id)
    assert reconcile == []


@pytest.mark.asyncio
async def test_expire_unpaid_unsettled_releases_without_credit(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """单笔超时关闭未结算订单：只清快照，不凭空退回积分、不建对账案件。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(db, order_id, points_used=5000, points_fen=5000)
    await order_service.expire_unpaid_order(order_id)
    assert await _points(db) == 100_000
    reconcile = await _reconcile_rows(db, order_id)
    assert reconcile == []


@pytest.mark.asyncio
async def test_batch_timeout_unsettled_releases_without_credit(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """批量超时扫描关闭未结算订单：只清快照，不凭空退回积分、不建对账案件。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(db, order_id, points_used=5000, points_fen=5000)
    order = await OrderRepo(db).get_order(order_id)
    payment = loads_payment(order.payment)
    old_created_at = (
        datetime.now() - timedelta(minutes=PAYMENT_TIMEOUT_MINUTES + 1)
    ).strftime("%Y-%m-%d %H:%M:%S")
    payment["createdAt"] = old_created_at
    await OrderRepo(db).update_payment(order_id, dumps_payment(payment), now_text())
    await db.commit()
    result = await order_service.expire_timeout_unpaid_orders()
    assert result["expiredCount"] == 1
    assert await _points(db) == 100_000
    reconcile = await _reconcile_rows(db, order_id)
    assert reconcile == []


@pytest.mark.asyncio
async def test_unsettled_direct_refund_creates_no_case(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """未结算订单直接 refund：只清快照，不建对账案件（两命令分流）。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(db, order_id, points_used=5000, points_fen=5000)
    order = await OrderRepo(db).get_order(order_id)
    await points_service.refund_points(order)
    await points_service.refund_points(order)
    assert await _points(db) == 100_000
    reconcile = await _reconcile_rows(db, order_id)
    assert reconcile == []


@pytest.mark.asyncio
async def test_settled_refund_missing_redeem_creates_case_without_credit(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """已结算但 redeem 流水缺失：不得误判为未结算释放，进可关闭对账案件且不自动 credit。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(
        db,
        order_id,
        points_used=5000,
        points_fen=5000,
        points_awarded=0,
        settled=True,
    )
    order = await OrderRepo(db).get_order(order_id)
    await points_service.refund_points(order)
    assert await _points(db) == 100_000
    reconcile = await _reconcile_rows(db, order_id)
    assert len(reconcile) == 1
    assert reconcile[0]["reason"] == "redeem_missing"
    assert reconcile[0]["status"] == "open"
    # 幂等：再次退款不重复建案
    await points_service.refund_points(order)
    assert len(await _reconcile_rows(db, order_id)) == 1


@pytest.mark.asyncio
async def test_settled_refund_redeem_mismatch_creates_case_without_credit(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """已结算且 redeem 流水金额与快照不一致：进可关闭对账案件且不自动 credit。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(
        db,
        order_id,
        points_used=5000,
        points_fen=5000,
        points_awarded=0,
        settled=True,
    )
    # 伪造金额不一致的 redeem 流水（实际只扣过 3000 分）
    await db.execute(
        "INSERT INTO points_ledger (unique_id, customer_id, mobile, amount, total, "
        "event_type, source, biz_type, biz_id, occurred_at, created_at) "
        "VALUES (?, 'cm_x', ?, -3000, 0, 'order_redeem', 'order', "
        "'order_redeem', ?, datetime('now'), datetime('now'))",
        (f"points:redeem:{order_id}", MOBILE, order_id),
    )
    await db.commit()
    order = await OrderRepo(db).get_order(order_id)
    await points_service.refund_points(order)
    assert await _points(db) == 100_000
    reconcile = await _reconcile_rows(db, order_id)
    assert len(reconcile) == 1
    assert reconcile[0]["reason"] == "redeem_mismatch"


@pytest.mark.asyncio
async def test_refund_credits_to_original_ledger_mobile(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """已结算退款按原流水账户入账（当前手机号变化不影响退款归属）。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(db, order_id, points_used=5000, points_fen=5000)
    await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    assert await _points(db) == 95_050
    # 模拟原扣减账户与当前解析手机号不同：改写 redeem 流水 mobile
    await db.execute(
        "UPDATE points_ledger SET mobile = ? WHERE unique_id = ?",
        (MOBILE_ORIGINAL, f"points:redeem:{order_id}"),
    )
    await db.commit()
    order = await OrderRepo(db).get_order(order_id)
    await points_service.refund_points(order)
    # 退回积分应落入原流水账户
    rows = await db.execute_fetchall(
        "SELECT mobile, amount FROM points_ledger WHERE unique_id = ?",
        (f"points:refund:{order.id}",),
    )
    assert rows and rows[0]["mobile"] == MOBILE_ORIGINAL
    assert rows[0]["amount"] == 5000
    reconcile = await _reconcile_rows(db, order_id)
    assert reconcile == []


@pytest.mark.asyncio
async def test_reconcile_case_closable(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """对账案件人工核对后可关闭（open→closed，幂等）。"""
    from app.repository.points_refund_reconcile_repo import PointsRefundReconcileRepo

    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(
        db,
        order_id,
        points_used=5000,
        points_fen=5000,
        points_awarded=0,
        settled=True,
    )
    order = await OrderRepo(db).get_order(order_id)
    await points_service.refund_points(order)
    repo = PointsRefundReconcileRepo(db)
    assert await repo.close_open(order_id=order_id, reason="redeem_missing") is True
    assert await repo.close_open(order_id=order_id, reason="redeem_missing") is False
    rows = await db.execute_fetchall(
        "SELECT status FROM points_refund_reconcile WHERE order_id = ?",
        (order_id,),
    )
    assert rows and rows[0]["status"] == "closed"


@pytest.mark.asyncio
async def test_refund_points_skips_clawback_without_award_entry(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """已结算但已发积分流水缺失时跳过收回并记录对账案件（不凭空扣分）。"""
    await _seed_member(db, points=1000)
    order_id = await _create_order(order_service, price_fen=10_000)
    order = await OrderRepo(db).get_order(order_id)
    payment = loads_payment(order.payment)
    payment["pointsUsed"] = 0
    payment["pointsFen"] = 0
    payment["pointsAwarded"] = 100
    payment["pointsSettledAt"] = now_text()
    await OrderRepo(db).update_payment(order_id, dumps_payment(payment), now_text())
    await db.commit()
    await points_service.refund_points(await OrderRepo(db).get_order(order_id))
    assert await _points(db) == 1000
    reconcile = await _reconcile_rows(db, order_id)
    assert reconcile and reconcile[0]["reason"] == "award_missing"


@pytest.mark.asyncio
async def test_settled_refund_credits_and_does_not_log_reconcile(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """已结算退款正常退回积分并收回已发积分，不产生对账修正记录。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(db, order_id, points_used=5000, points_fen=5000)
    await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    order = await OrderRepo(db).get_order(order_id)
    await points_service.refund_points(order)
    assert await _points(db) == 100_000
    reconcile = await _reconcile_rows(db, order_id)
    assert reconcile == []


# ==================== B3.5（评审问题 2 / 3）====================


@pytest.mark.asyncio
async def test_apply_points_binds_member_balance_id(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """问题 2：应用积分时快照绑定不可变余额账户 ID。"""
    monkeypatch.setattr("app.service.points.payment.POINTS_DEDUCTION_FENCE", False)
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await points_service.apply_points(order_id, user_id=USER_ID)
    order = await OrderRepo(db).get_order(order_id)
    payment = loads_payment(order.payment)
    rows = await db.execute_fetchall(
        "SELECT id FROM member_balance WHERE mobile = ?", (MOBILE,)
    )
    assert rows
    assert str(payment.get("memberBalanceId")) == str(rows[0]["id"])


@pytest.mark.asyncio
async def test_apply_points_rejects_missing_account(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """问题 2：积分账户不存在（member_balance 无行）禁止应用抵扣。"""
    monkeypatch.setattr("app.service.points.payment.POINTS_DEDUCTION_FENCE", False)
    # 只建客户身份，不建 member_balance 账户
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '积分账户缺失测试', 'high', 1)",
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
    await db.commit()
    order_id = await _create_order(order_service, price_fen=10_000)
    with pytest.raises(ValueError, match="积分账户不存在"):
        await points_service.apply_points(order_id, user_id=USER_ID)
    order = await OrderRepo(db).get_order(order_id)
    assert str(loads_payment(order.payment).get("status")) == "unpaid"


@pytest.mark.asyncio
async def test_award_blocks_when_points_account_missing(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """问题 2：有抵扣但积分账户不存在 → 结算被拒，订单保持未支付（禁止免费抵扣）。"""
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '结算账户缺失测试', 'high', 1)",
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
    await db.commit()
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(db, order_id, points_used=5000, points_fen=5000)
    with pytest.raises(ValueError, match="积分账户不存在"):
        await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    order = await OrderRepo(db).get_order(order_id)
    assert str(loads_payment(order.payment).get("status")) == "partial"


@pytest.mark.asyncio
async def test_award_blocks_when_account_switched_after_apply(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """问题 2：应用后换绑账户 → 结算按快照绑定账户校验拒绝（账户漂移）。"""
    monkeypatch.setattr("app.service.points.payment.POINTS_DEDUCTION_FENCE", False)
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await points_service.apply_points(order_id, user_id=USER_ID)
    # 换绑：客户手机号改为新号，且新号有独立账户行
    await db.execute(
        "UPDATE customer_master SET primary_phone = ? WHERE id = ?",
        ("13900000099", f"cm_{OPENID}"),
    )
    await db.execute(
        "INSERT INTO member_balance (mobile, points) VALUES (?, 100000)",
        ("13900000099",),
    )
    await db.commit()
    with pytest.raises(ValueError, match="积分账户已变更"):
        await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    order = await OrderRepo(db).get_order(order_id)
    assert str(loads_payment(order.payment).get("status")) == "partial"


@pytest.mark.asyncio
async def test_settled_refund_writes_facts_and_clears_snapshot(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """问题 3：退款全成功 → 结算/退款事实链 + refund_operation succeeded + 快照清除。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(db, order_id, points_used=5000, points_fen=5000)
    await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    order = await OrderRepo(db).get_order(order_id)
    await points_service.refund_points(order)
    assert await _points(db) == 100_000
    facts = await db.execute_fetchall(
        "SELECT operation_type, amount FROM ledger_operation "
        "WHERE subject_type = 'order' AND subject_id = ? ORDER BY id ASC",
        (order_id,),
    )
    assert [row["operation_type"] for row in facts] == [
        "settle_redeem",
        "settle_award",
        "refund_return",
        "refund_clawback",
    ]
    assert int(facts[0]["amount"]) == -5000
    assert int(facts[3]["amount"]) == -50
    ops = await db.execute_fetchall(
        "SELECT status, return_amount, clawback_amount FROM refund_operation "
        "WHERE order_id = ?",
        (order_id,),
    )
    assert ops and ops[0]["status"] == "succeeded"
    assert int(ops[0]["return_amount"]) == 5000
    assert int(ops[0]["clawback_amount"]) == 50
    payment = loads_payment((await OrderRepo(db).get_order(order_id)).payment)
    assert int(payment.get("pointsUsed") or 0) == 0
    assert int(payment.get("pointsAwarded") or 0) == 0


@pytest.mark.asyncio
async def test_refund_shortfall_keeps_snapshot_and_writes_debt(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """问题 3：奖励积分扣回余额不足 → 欠账 + 保留事实快照（补偿未终结）。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    await _seed_points_partial(db, order_id, points_used=5000, points_fen=5000)
    await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    # 已发积分账面划入无余额账户（模拟原发分账户已空），clawback 扣回失败
    await db.execute(
        "UPDATE points_ledger SET mobile = '13900000000' WHERE unique_id = ?",
        (f"points:award:{order_id}",),
    )
    await db.commit()
    order = await OrderRepo(db).get_order(order_id)
    await points_service.refund_points(order)
    # return 退回 5000；clawback 失败 → 欠账 50，不静默跳过
    assert await _points(db) == 100_050
    debts = await db.execute_fetchall(
        "SELECT amount, status, operation_key FROM refund_shortfall_debt "
        "WHERE order_id = ?",
        (order_id,),
    )
    assert debts and int(debts[0]["amount"]) == 50
    assert debts[0]["status"] == "open"
    assert debts[0]["operation_key"] == f"points:refund:{order_id}:clawback"
    ops = await db.execute_fetchall(
        "SELECT status, shortfall_amount FROM refund_operation WHERE order_id = ?",
        (order_id,),
    )
    assert ops and ops[0]["status"] == "shortfall"
    assert int(ops[0]["shortfall_amount"]) == 50
    # 补偿未终结：事实快照保留（pointsUsed 不清零），可重试
    payment = loads_payment((await OrderRepo(db).get_order(order_id)).payment)
    assert int(payment.get("pointsUsed") or 0) == 5000
    assert payment.get("pointsSettledAt")


# ==================== B3.5（评审问题 5：双连接真实并发）====================


@pytest.mark.asyncio
async def test_dual_connection_concurrent_settle_single_winner(
    tmp_path,
) -> None:
    """问题 5：两个数据库连接 + 同步屏障并发结算同一订单，只有一个活跃尝试胜出。

    评审指出 B3.4 的「并发测试」为顺序执行（同一连接）；本测试用独立连接
    与 asyncio.Barrier 制造真实并发。WAL 读升写竞争下败者可能得到瞬时
    `database is locked`（SQLite 死锁回避，非 busy 重试），或 CAS 冲突
    ValueError——两条路径都不会产生第二个活跃尝试；结算事实（积分流水 /
    余额 / 订单状态）只出现一次。
    """
    import asyncio
    import sqlite3

    from app.database import close_db, init_db
    from app.repository.base import DatabaseHandle
    from tests.helpers.catalog_seed import seed_catalog_product

    db_path = tmp_path / "dual_settle.db"
    conn_a = await init_db(str(db_path))
    conn_b = await init_db(str(db_path))
    try:
        handle_a = DatabaseHandle(conn_a)
        handle_b = DatabaseHandle(conn_b)
        await seed_catalog_product(
            conn_a,
            item_id=81099,
            title="并发结算蛋糕",
            price_fen=10_000,
            stock=8,
        )
        await conn_a.commit()

        def build_service(handle: DatabaseHandle) -> OrderApplicationService:
            return OrderApplicationService(
                order_repo=OrderRepo(handle),
                event_repo=OrderEventRepo(handle),
                session_repo=SessionRepo(handle),
                product_repo=YouzanProductRepo(handle),
                inventory_repo=YouzanInventoryRepo(handle),
                config_repo=ConfigRepo(handle),
            )

        seeder = build_service(handle_a)
        created = await seeder.create_order(
            {
                "items": [
                    {
                        "productId": "81099",
                        "title": "并发结算蛋糕",
                        "priceFen": 10_000,
                        "quantity": 1,
                    }
                ],
                "receiverName": "并发测试",
                "receiverPhone": "18800000099",
                "deliveryType": "delivery",
                "deliveryAddress": "并发测试地址",
                "expectTime": "2026-08-20 19:00",
            },
            user_id="wx_openid_dual_001",
        )
        order_id = created["orderId"]
        # 直写积分抵扣 partial（结算将产生可观测的积分流水，用于证明只结算一次）
        order = await OrderRepo(conn_a).get_order(order_id)
        payment = loads_payment(order.payment)
        payment.update(
            {
                "status": "partial",
                "method": "combined",
                "pointsUsed": 5000,
                "pointsFen": 5000,
                "remainFen": 5000,
            }
        )
        await OrderRepo(conn_a).update_payment(
            order_id, dumps_payment(payment), now_text()
        )
        await conn_a.commit()
        # 并发结算前先建好客户身份与积分账户（扣减目标）
        await conn_a.execute(
            "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
            "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
            "VALUES ('cm_dual_001', 'yunxi', 'active', '18800000099', 1, "
            "'并发结算测试', 'high', 1)"
        )
        await conn_a.execute(
            "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
            "identity_type, identity_value, identity_value_normalized, source_system, "
            "link_status, verification_status, confidence_score) "
            "VALUES ('cil_dual_001', 'yunxi', 'cm_dual_001', 'miniapp_openid', "
            "'openid_dual_001', 'openid_dual_001', 'miniapp', 'active', 'verified', 100)"
        )
        await conn_a.execute(
            "INSERT INTO member_balance (mobile, points) VALUES ('18800000099', 100000)"
        )
        await conn_a.commit()

        svc_a = build_service(handle_a)
        svc_b = build_service(handle_b)
        barrier = asyncio.Barrier(2)

        async def attempt(svc: OrderApplicationService) -> str:
            await barrier.wait()
            try:
                await svc.confirm_mock_payment(order_id, user_id="wx_openid_dual_001")
                return "ok"
            except ValueError:
                return "conflict"
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                return "locked"

        results = await asyncio.gather(attempt(svc_a), attempt(svc_b))
        # 恰有一个活跃尝试胜出；败者要么 CAS 冲突，要么瞬时锁（读升写竞争）
        assert results.count("ok") == 1
        assert set(results) == {"ok", "conflict"} or set(results) == {"ok", "locked"}
        # 结算事实只出现一次：积分流水恰 2 条（redeem + award），余额唯一
        rows = await conn_a.execute_fetchall(
            "SELECT COUNT(*) AS c FROM points_ledger WHERE biz_id = ?", (order_id,)
        )
        assert int(rows[0]["c"]) == 2
        balance = await conn_a.execute_fetchall(
            "SELECT points FROM member_balance WHERE mobile = '18800000099'"
        )
        assert balance and int(balance[0]["points"]) == 95_050
        orders = await conn_a.execute_fetchall(
            "SELECT payment FROM orders WHERE id = ?", (order_id,)
        )
        assert orders
        assert str(loads_payment(str(orders[0]["payment"])).get("status")) == "paid"
    finally:
        await close_db(conn_a)
        await close_db(conn_b)
