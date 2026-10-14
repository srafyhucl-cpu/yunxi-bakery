"""会员储值余额 M2 测试：充值入账 / 余额支付 / 组合支付与退款闭环。"""

import json

import aiosqlite
import pytest

from app.config import settings
from app.models.coupon import CouponTemplate, CouponType
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.models.order import Order

from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.config_repo import ConfigRepo
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.recharge_repo import RechargeRepo
from app.repository.session_repo import SessionRepo
from app.service.integrations.wechat_pay import WechatPayPrepayResult
from app.service.order.payment_notification import WechatPaymentNotificationService
from app.service.order import OrderApplicationService
from app.service.coupon import CouponService
from app.service.order.payment_state import dumps_payment, loads_payment
from app.service.stored_value import (
    MemberBalanceService,
    RechargeService,
    StoredValueOrderPaymentService,
    StoredValueService,
)
from tests.helpers.legacy_order_catalog import (
    LegacyOrderInventoryRepo,
    LegacyOrderProductRepo,
)

MOBILE = "13800000001"
OPENID = "openid_m2_001"
USER_ID = f"wx_{OPENID}"


async def _seed_member(
    db: aiosqlite.Connection,
    *,
    openid: str = OPENID,
    mobile: str = MOBILE,
    balance_fen: int = 0,
) -> None:
    """落库客户主档 + 小程序身份链接 + 会员余额账户。"""
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '测试会员', 'high', 1)",
        (f"cm_{openid}", mobile),
    )
    await db.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (f"cil_{openid}", f"cm_{openid}", openid, openid),
    )
    if balance_fen:
        await db.execute(
            "INSERT INTO member_balance (mobile, stored_value_fen) VALUES (?, ?)",
            (mobile, balance_fen),
        )
    await db.commit()


@pytest.fixture
def stored_value_service(db: aiosqlite.Connection) -> StoredValueService:
    """使用真实内存库仓储构建储值域服务。"""
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    return StoredValueService(
        member_service=member_service,
        recharge_service=RechargeService(
            recharge_repo=RechargeRepo(db),
            member_service=member_service,
        ),
        payment_service=StoredValueOrderPaymentService(
            order_repo=OrderRepo(db),
            member_service=member_service,
        ),
    )


@pytest.fixture
def order_service(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
) -> OrderApplicationService:
    """构建订单应用服务并接入储值退款钩子。"""
    return OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=LegacyOrderProductRepo(db),
        inventory_repo=LegacyOrderInventoryRepo(db),
        config_repo=ConfigRepo(db),
        stored_value_service=stored_value_service,
    )


async def _create_order(
    order_service: OrderApplicationService,
    *,
    price_fen: int = 5000,
    user_id: str = USER_ID,
) -> str:
    created = await order_service.create_order(
        {
            "items": [
                {
                    "productId": "p_m2_001",
                    "title": "M2 储值测试蛋糕",
                    "priceFen": price_fen,
                    "quantity": 1,
                }
            ],
            "receiverName": "储值测试",
            "receiverPhone": MOBILE,
            "deliveryType": "pickup",
            "deliveryAddress": "储值测试地址",
            "expectTime": "2026-08-20 19:00",
        },
        user_id=user_id,
    )
    return created["orderId"]


async def _seed_coupon(db: aiosqlite.Connection) -> None:
    """落库一张可用于组合支付的本地优惠券。"""
    await CouponTemplateRepo(db).upsert_from_youzan(
        CouponTemplate(
            id="cg-late-cancel",
            name="迟到支付测试券",
            coupon_type=CouponType.FULL_REDUCTION,
            threshold_fen=3000,
            value_fen=500,
            valid_from="2026-01-01",
            valid_until="2026-12-31",
        )
    )
    await CouponInventoryRepo(db).insert(
        CouponInventoryEntry(
            coupon_id="coupon-late-cancel",
            coupon_group_id="cg-late-cancel",
            mobile=MOBILE,
            status=CouponStatus.TAKE,
            title="迟到支付测试券",
            value_fen=500,
            source=LedgerSource.IMPORT,
            occurred_at="2026-09-25 09:00:00",
            template_id="cg-late-cancel",
            valid_from="2026-01-01",
            valid_until="2026-12-31",
        )
    )
    await db.commit()


async def _balance_fen(db: aiosqlite.Connection) -> int:
    rows = await db.execute_fetchall(
        "SELECT stored_value_fen FROM member_balance WHERE mobile = ? LIMIT 1",
        (MOBILE,),
    )
    return int(rows[0]["stored_value_fen"]) if rows else 0


async def _points_balance(db: aiosqlite.Connection) -> int:
    rows = await db.execute_fetchall(
        "SELECT points FROM member_balance WHERE mobile = ? LIMIT 1",
        (MOBILE,),
    )
    return int(rows[0]["points"]) if rows else 0


async def _ledger_rows(db: aiosqlite.Connection) -> list[dict]:
    return await db.execute_fetchall(
        "SELECT unique_id, amount_fen, biz_type, biz_id, balance_after_fen "
        "FROM balance_ledger WHERE mobile = ? ORDER BY id ASC",
        (MOBILE,),
    )


async def test_stored_value_tables_created(db: aiosqlite.Connection) -> None:
    """初始化数据库后应包含充值单与余额流水表及关键字段。"""
    recharge_columns = [
        row["name"]
        for row in await db.execute_fetchall("PRAGMA table_info(stored_value_recharge)")
    ]
    assert {"id", "user_id", "mobile", "amount_fen", "status"}.issubset(
        recharge_columns
    )
    ledger_columns = [
        row["name"]
        for row in await db.execute_fetchall("PRAGMA table_info(balance_ledger)")
    ]
    assert {
        "unique_id",
        "amount_fen",
        "balance_after_fen",
        "biz_type",
        "biz_id",
    }.issubset(ledger_columns)


@pytest.mark.asyncio
async def test_recharge_mock_pay_credits_balance_once(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
) -> None:
    """mock 充值应入账余额并写流水，重复确认不重复入账。"""
    await _seed_member(db)
    created = await stored_value_service.create_recharge(USER_ID, 5000)
    assert created["status"] == "unpaid"
    paid = await stored_value_service.confirm_mock_recharge_payment(
        created["rechargeId"], user_id=USER_ID
    )
    assert paid["status"] == "paid"
    assert paid["paymentMethod"] == "mock"
    assert await _balance_fen(db) == 5000
    # 重复确认幂等
    again = await stored_value_service.confirm_mock_recharge_payment(
        created["rechargeId"], user_id=USER_ID
    )
    assert again["status"] == "paid"
    assert await _balance_fen(db) == 5000
    ledger = await _ledger_rows(db)
    assert len(ledger) == 1
    assert ledger[0]["biz_type"] == "recharge"
    assert ledger[0]["amount_fen"] == 5000


@pytest.mark.asyncio
async def test_recharge_amount_bounds_and_cancel(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
) -> None:
    """充值金额上下限校验；未支付充值单可取消，已支付不可取消。"""
    await _seed_member(db)
    with pytest.raises(ValueError, match="充值金额不能低于"):
        await stored_value_service.create_recharge(USER_ID, 50)
    with pytest.raises(ValueError, match="充值金额不能超过"):
        await stored_value_service.create_recharge(USER_ID, 50_001)
    accepted = await stored_value_service.create_recharge(USER_ID, 50_000)
    assert accepted["status"] == "unpaid"
    cancelled = await stored_value_service.cancel_unpaid_recharge(
        accepted["rechargeId"], user_id=USER_ID
    )
    assert cancelled["status"] == "cancelled"
    assert await _balance_fen(db) == 0
    second = await stored_value_service.create_recharge(USER_ID, 1000)
    await stored_value_service.confirm_mock_recharge_payment(
        second["rechargeId"], user_id=USER_ID
    )
    with pytest.raises(ValueError, match="当前充值单状态不允许取消"):
        await stored_value_service.cancel_unpaid_recharge(
            second["rechargeId"], user_id=USER_ID
        )


@pytest.mark.asyncio
async def test_unrecognized_user_rejected(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
) -> None:
    """未识别为会员的用户不能充值或查询余额。"""
    with pytest.raises(ValueError, match="当前用户未识别为会员"):
        await stored_value_service.create_recharge("wx_openid_unknown", 1000)
    with pytest.raises(ValueError, match="当前用户未识别为会员"):
        await stored_value_service.get_user_balance("wx_openid_unknown")


@pytest.mark.asyncio
async def test_pay_order_with_balance_success_and_idempotent(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """全额余额支付应扣款并置订单已支付，重复支付不重复扣款。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    paid = await stored_value_service.pay_order_with_balance(order_id, user_id=USER_ID)
    assert paid["paymentStatus"] == "paid"
    assert paid["paymentMethod"] == "balance"
    assert paid["balanceFen"] == 5000
    assert await _balance_fen(db) == 95_000
    again = await stored_value_service.pay_order_with_balance(order_id, user_id=USER_ID)
    assert again["paymentStatus"] == "paid"
    assert await _balance_fen(db) == 95_000
    ledger = await _ledger_rows(db)
    assert len(ledger) == 1
    assert ledger[0]["biz_type"] == "order_pay"
    assert ledger[0]["amount_fen"] == -5000


@pytest.mark.asyncio
async def test_pay_order_with_balance_insufficient_no_deduct(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """余额不足时余额支付应拒绝且不扣款、订单保持未支付。"""
    await _seed_member(db, balance_fen=3000)
    order_id = await _create_order(order_service, price_fen=5000)
    with pytest.raises(ValueError, match="储值余额不足"):
        await stored_value_service.pay_order_with_balance(order_id, user_id=USER_ID)
    assert await _balance_fen(db) == 3000
    detail = await order_service.get_user_order(order_id, user_id=USER_ID)
    assert detail["status"] == "pending"


@pytest.mark.asyncio
async def test_combined_payment_flow_and_remainder_mock_pay(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """组合支付：扣余额部分置中间态，差额 mock 完成后订单支付。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    combined = await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    assert combined["payment"]["status"] == "partial"
    assert combined["payment"]["balanceFen"] == 2000
    assert combined["payment"]["remainFen"] == 3000
    assert combined["remainderPayment"]["paymentMethod"] == "mock"
    assert await _balance_fen(db) == 98_000
    partial_detail = await order_service.get_user_order(order_id, user_id=USER_ID)
    assert partial_detail["balanceFen"] == 2000
    paid = await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    assert paid["paymentStatus"] == "paid"
    assert paid["paymentMethod"] == "combined"
    assert await _balance_fen(db) == 98_000
    ledger = await _ledger_rows(db)
    assert len(ledger) == 1
    assert ledger[0]["biz_id"] == order_id
    assert ledger[0]["amount_fen"] == -2000


@pytest.mark.asyncio
async def test_combined_payment_invalid_split_rejected(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """组合支付余额部分必须大于 0 且小于订单总额。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    with pytest.raises(ValueError, match="必须大于 0 且小于订单总额"):
        await stored_value_service.prepare_combined_payment(
            order_id, user_id=USER_ID, balance_fen=5000
        )
    with pytest.raises(ValueError, match="必须大于 0 且小于订单总额"):
        await stored_value_service.prepare_combined_payment(
            order_id, user_id=USER_ID, balance_fen=0
        )
    assert await _balance_fen(db) == 100_000


@pytest.mark.asyncio
async def test_combined_payment_user_cancel_refunds_balance(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """组合支付订单取消后应原路退回已扣余额，且不重复退款。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    assert await _balance_fen(db) == 98_000
    cancelled = await order_service.cancel_user_order(order_id, user_id=USER_ID)
    assert cancelled["status"] == "cancelled"
    assert await _balance_fen(db) == 100_000
    # 重复取消不重复退款
    await order_service.cancel_user_order(order_id, user_id=USER_ID)
    assert await _balance_fen(db) == 100_000
    ledger = await _ledger_rows(db)
    assert [row["biz_type"] for row in ledger] == ["order_pay", "order_refund"]
    assert ledger[1]["amount_fen"] == 2000


@pytest.mark.asyncio
async def test_late_wechat_payment_after_combined_cancel_keeps_external_refund_fact(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """组合支付取消后迟到到账，只记录微信差额待退款，不重复动余额。"""
    monkeypatch.setattr(
        "app.service.order.payment_runtime.settings.WECHAT_PAY_MCH_ID", "mch-test"
    )
    monkeypatch.setattr(
        "app.service.order.payment_runtime.settings.WECHAT_MINIAPP_APP_ID",
        "appid-test",
    )
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    assert await _balance_fen(db) == 98_000

    await order_service.cancel_user_order(order_id, user_id=USER_ID)
    assert await _balance_fen(db) == 100_000

    recovered = await order_service.reconcile_pay_from_query(
        {
            "out_trade_no": order_id,
            "trade_state": "SUCCESS",
            "mchid": "mch-test",
            "appid": "appid-test",
            "amount": {"total": 3000, "currency": "CNY"},
            "transaction_id": "4200000000202609251234567896",
            "success_time": "2026-09-25T12:00:00+08:00",
        }
    )

    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    assert order.status == "cancelled"
    assert payment["status"] == "paid"
    assert payment["method"] == "combined"
    assert payment["balanceFen"] == 2000
    assert payment["transactionId"] == "4200000000202609251234567896"
    assert payment["paidAt"] == "2026-09-25 12:00:00"
    assert payment["refundStatus"] == "pending"
    assert payment["refundAmountFen"] == 3000
    assert recovered["status"] == "cancelled"
    assert recovered["paymentStatus"] == "paid"
    assert await _balance_fen(db) == 100_000

    transactions = await db.execute_fetchall(
        "SELECT order_id FROM payment_transactions WHERE transaction_id = ?",
        ("4200000000202609251234567896",),
    )
    assert len(transactions) == 1
    assert transactions[0]["order_id"] == order_id
    events = await OrderEventRepo(db).list_by_order(order_id)
    assert {event.status for event in events} == {"pending", "cancelled", "paid"}


@pytest.mark.asyncio
async def test_late_wechat_refund_after_combined_cancel_refunds_external_leg_once(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """组合支付取消后，迟到外部支付的全额退款只退微信腿一次。"""
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-late-refund")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-late-refund")
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    assert await _balance_fen(db) == 98_000

    await order_service.cancel_user_order(order_id, user_id=USER_ID)
    assert await _balance_fen(db) == 100_000

    payment_transaction = {
        "out_trade_no": order_id,
        "trade_state": "SUCCESS",
        "mchid": "mch-late-refund",
        "appid": "appid-late-refund",
        "amount": {"total": 3000, "currency": "CNY"},
        "transaction_id": "4200000000202609251234567897",
        "success_time": "2026-09-25T12:00:00+08:00",
    }
    refund_transaction = {
        "mchid": "mch-late-refund",
        "out_trade_no": order_id,
        "transaction_id": "4200000000202609251234567897",
        "out_refund_no": "R-LATE-COMBINED",
        "refund_id": "wx-R-LATE-COMBINED",
        "refund_status": "SUCCESS",
        "success_time": "2026-09-25T12:05:00+08:00",
        "amount": {
            "total": 3000,
            "refund": 3000,
            "payer_total": 3000,
            "payer_refund": 3000,
        },
    }
    monkeypatch.setattr(
        "app.service.order.payment_runtime.OrderPaymentRuntimeService"
        "._verify_wechat_notify_signature",
        lambda self, raw_body, headers: True,
    )
    monkeypatch.setattr(
        "app.service.order.payment_runtime.OrderPaymentRuntimeService"
        "._decrypt_wechat_resource",
        lambda self, resource: payment_transaction,
    )
    paid = await order_service.handle_wechat_payment_notify(
        raw_body=json.dumps({"id": "EV-late-combined-pay", "resource": {}}).encode(
            "utf-8"
        ),
        headers={},
    )
    assert paid["status"] == "cancelled"
    assert paid["paymentRefundAmountFen"] == 3000

    monkeypatch.setattr(
        "app.service.order.payment_runtime.OrderPaymentRuntimeService"
        "._decrypt_wechat_resource",
        lambda self, resource: refund_transaction,
    )
    refund = await order_service.handle_wechat_refund_notify(
        raw_body=json.dumps({"id": "EV-late-combined-refund", "resource": {}}).encode(
            "utf-8"
        ),
        headers={},
    )
    duplicate = await order_service.handle_wechat_refund_notify(
        raw_body=json.dumps({"id": "EV-late-combined-refund", "resource": {}}).encode(
            "utf-8"
        ),
        headers={},
    )

    assert refund["kind"] == "acknowledged"
    assert duplicate.get("kind") == "duplicate"
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    assert order.status == "cancelled"
    assert payment["status"] == "paid"
    assert payment["refundStatus"] == "full"
    assert payment["refundFen"] == 3000
    assert await _balance_fen(db) == 100_000
    assert await _points_balance(db) == 0
    ledger = await _ledger_rows(db)
    assert [row["biz_type"] for row in ledger] == ["order_pay", "order_refund"]
    assert [row["amount_fen"] for row in ledger] == [-2000, 2000]


@pytest.mark.asyncio
async def test_cancelled_coupon_combined_payment_late_notify_uses_original_external_leg(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """使用优惠券的组合支付取消后，迟到通知仍按原微信腿金额入账。"""
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-late-coupon")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-late-coupon")
    await _seed_member(db, balance_fen=100_000)
    await _seed_coupon(db)
    order_id = await _create_order(order_service, price_fen=5000)
    coupon_service = CouponService(
        order_repo=OrderRepo(db),
        customer_repo=CustomerMasterRepo(db),
        template_repo=CouponTemplateRepo(db),
        inventory_repo=CouponInventoryRepo(db),
    )
    applied = await coupon_service.apply_coupon(
        order_id, user_id=USER_ID, coupon_id="coupon-late-cancel"
    )
    assert applied["couponFen"] == 500
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    assert loads_payment(order.payment)["remainFen"] == 2500
    assert loads_payment(order.payment)["externalPaidFen"] == 2500

    await order_service.cancel_user_order(order_id, user_id=USER_ID)
    assert await _balance_fen(db) == 100_000

    transaction = {
        "out_trade_no": order_id,
        "trade_state": "SUCCESS",
        "mchid": "mch-late-coupon",
        "appid": "appid-late-coupon",
        "amount": {"total": 2500, "currency": "CNY"},
        "transaction_id": "4200000000202609251234567898",
        "success_time": "2026-09-25T12:00:00+08:00",
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
    result = await order_service.handle_wechat_payment_notify(
        raw_body=json.dumps({"id": "EV-late-coupon-pay", "resource": {}}).encode(
            "utf-8"
        ),
        headers={},
    )

    assert result["status"] == "cancelled"
    assert result["paymentRefundAmountFen"] == 2500

    refund_transaction = {
        "mchid": "mch-late-coupon",
        "out_trade_no": order_id,
        "transaction_id": "4200000000202609251234567898",
        "out_refund_no": "R-LATE-COUPON",
        "refund_id": "wx-R-LATE-COUPON",
        "refund_status": "SUCCESS",
        "success_time": "2026-09-25T12:05:00+08:00",
        "amount": {
            "total": 2500,
            "refund": 2500,
            "payer_total": 2500,
            "payer_refund": 2500,
        },
    }
    monkeypatch.setattr(
        "app.service.order.payment_runtime.OrderPaymentRuntimeService"
        "._decrypt_wechat_resource",
        lambda self, resource: refund_transaction,
    )
    refund = await order_service.handle_wechat_refund_notify(
        raw_body=json.dumps({"id": "EV-late-coupon-refund", "resource": {}}).encode(
            "utf-8"
        ),
        headers={},
    )
    duplicate = await order_service.handle_wechat_refund_notify(
        raw_body=json.dumps({"id": "EV-late-coupon-refund", "resource": {}}).encode(
            "utf-8"
        ),
        headers={},
    )

    assert refund["kind"] == "acknowledged"
    assert duplicate["kind"] == "duplicate"
    order = await OrderRepo(db).get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    assert order.status == "cancelled"
    assert payment["refundStatus"] == "full"
    assert payment["refundFen"] == 2500
    assert await _balance_fen(db) == 100_000
    assert await _points_balance(db) == 0
    ledger = await _ledger_rows(db)
    assert [row["biz_type"] for row in ledger] == ["order_pay", "order_refund"]
    assert [row["amount_fen"] for row in ledger] == [-2000, 2000]


@pytest.mark.asyncio
async def test_combined_payment_timeout_expire_refunds_balance(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """组合支付订单超时关闭后应原路退回已扣余额。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    assert await _balance_fen(db) == 98_000
    expired = await order_service.expire_unpaid_order(order_id)
    assert expired["status"] == "cancelled"
    assert await _balance_fen(db) == 100_000


@pytest.mark.asyncio
async def test_admin_cancel_partial_order_refunds_balance(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """后台取消组合支付订单应原路退回已扣余额。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    assert await _balance_fen(db) == 98_000
    cancelled = await order_service.update_admin_order_status(order_id, "cancelled")
    assert cancelled["status"] == "cancelled"
    assert await _balance_fen(db) == 100_000


@pytest.mark.asyncio
@pytest.mark.parametrize("close_method", ["cancel", "expire", "admin"])
async def test_close_partial_order_retries_balance_refund_after_compensation_failure(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
    close_method: str,
) -> None:
    """关单补偿失败时应整体回滚，并允许后续重试余额退款。"""
    from app.service.points.payment import PointsPaymentService

    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    original_refund_points = PointsPaymentService.refund_points

    async def _raise_compensation_failure(self, order: Order) -> None:
        del self, order
        raise RuntimeError("注入积分补偿失败")

    monkeypatch.setattr(
        PointsPaymentService,
        "refund_points",
        _raise_compensation_failure,
    )

    async def close_order() -> dict:
        if close_method == "cancel":
            return await order_service.cancel_user_order(order_id, user_id=USER_ID)
        if close_method == "expire":
            return await order_service.expire_unpaid_order(order_id)
        return await order_service.update_admin_order_status(order_id, "cancelled")

    with pytest.raises(RuntimeError, match="注入积分补偿失败"):
        await close_order()

    pending_order = await OrderRepo(db).get_order(order_id)
    assert pending_order is not None
    assert pending_order.status == "pending"
    assert loads_payment(pending_order.payment)["status"] == "partial"
    assert await _balance_fen(db) == 98_000
    assert [row["biz_type"] for row in await _ledger_rows(db)] == ["order_pay"]

    monkeypatch.setattr(
        PointsPaymentService,
        "refund_points",
        original_refund_points,
    )
    closed = await close_order()

    assert closed["status"] == "cancelled"
    assert await _balance_fen(db) == 100_000
    assert [row["biz_type"] for row in await _ledger_rows(db)] == [
        "order_pay",
        "order_refund",
    ]


@pytest.mark.asyncio
async def test_admin_close_refunded_combined_order_does_not_refund_balance_twice(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全额退款后关单不得重复入账，退款通知已完成的余额补偿只记一次。"""
    await _seed_member(db, balance_fen=100_000)
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-refunded-close")
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    assert await _balance_fen(db) == 98_000

    await order_service.reconcile_refund_from_query(
        {
            "mchid": "mch-refunded-close",
            "out_trade_no": order_id,
            "transaction_id": f"wx-{order_id}",
            "out_refund_no": f"R-{order_id}",
            "refund_id": f"refund-{order_id}",
            "refund_status": "SUCCESS",
            "success_time": "2026-08-20T12:00:00+08:00",
            "amount": {
                "total": 3000,
                "refund": 3000,
                "payer_total": 3000,
                "payer_refund": 3000,
            },
        },
        payer_total_fen=3000,
    )
    assert await _balance_fen(db) == 100_000

    cancelled = await order_service.update_admin_order_status(order_id, "cancelled")
    assert cancelled["status"] == "cancelled"
    assert await _balance_fen(db) == 100_000
    assert [row["biz_type"] for row in await _ledger_rows(db)] == [
        "order_pay",
        "order_refund",
    ]


@pytest.mark.asyncio
async def test_balance_paid_order_cannot_be_cancelled_or_refunded(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """全额余额支付后订单不可取消，已扣余额不原路退回。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.pay_order_with_balance(order_id, user_id=USER_ID)
    assert await _balance_fen(db) == 95_000
    with pytest.raises(ValueError, match="已支付订单不允许取消"):
        await order_service.cancel_user_order(order_id, user_id=USER_ID)
    with pytest.raises(ValueError, match="已支付订单不允许取消"):
        await order_service.update_admin_order_status(order_id, "cancelled")
    assert await _balance_fen(db) == 95_000
    ledger = await _ledger_rows(db)
    assert [row["biz_type"] for row in ledger] == ["order_pay"]


@pytest.mark.asyncio
async def test_combined_payment_prepare_twice_and_mock_confirm_idempotent(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """组合支付不可重复准备；差额 mock 完成后重复确认不重复扣款。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    with pytest.raises(ValueError, match="订单已部分支付"):
        await stored_value_service.prepare_combined_payment(
            order_id, user_id=USER_ID, balance_fen=1000
        )
    assert await _balance_fen(db) == 98_000
    await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    again = await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    assert again["paymentStatus"] == "paid"
    assert await _balance_fen(db) == 98_000
    ledger = await _ledger_rows(db)
    assert len(ledger) == 1
    assert ledger[0]["amount_fen"] == -2000


@pytest.mark.asyncio
async def test_combined_payment_remainder_can_resume_after_external_cancel(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """组合支付外部支付取消后仍可用余额快照继续完成剩余支付。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    combined = await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    assert combined["payment"]["status"] == "partial"

    resumed = await order_service.prepare_payment(order_id, user_id=USER_ID)
    assert resumed["paymentStatus"] == "unpaid"
    assert resumed["paymentMethod"] == "mock"

    paid = await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    assert paid["paymentStatus"] == "paid"
    assert await _balance_fen(db) == 98_000


@pytest.mark.asyncio
@pytest.mark.parametrize("refund_status", ["full", "over"])
async def test_prepare_payment_rejects_refunded_partial_order_without_prepay(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
    refund_status: str,
) -> None:
    """退款终态组合支付订单不得重新创建微信预下单会话。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    order_repo = OrderRepo(db)
    order = await order_repo.get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    payment["refundStatus"] = refund_status
    await order_repo.update_payment(
        order_id, dumps_payment(payment), "2026-08-20 19:00"
    )

    runtime = order_service._payment_service._payment_service
    prepay_calls: list[dict] = []

    async def fake_create_jsapi_prepay(**kwargs: object) -> WechatPayPrepayResult:
        prepay_calls.append(kwargs)
        return WechatPayPrepayResult(
            prepay_id=f"wx-prepay-{order_id}", appid="wx-app-id"
        )

    monkeypatch.setattr(runtime._wechat_pay_service, "is_ready", lambda: True)
    monkeypatch.setattr(
        runtime._wechat_pay_service,
        "create_jsapi_prepay",
        fake_create_jsapi_prepay,
    )
    monkeypatch.setattr(runtime, "_sign_with_rsa", lambda message: "signed-pay-params")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "wx-app-id")

    with pytest.raises(ValueError, match="订单已退款，不能继续支付"):
        await order_service.prepare_payment(order_id, user_id=USER_ID)

    assert prepay_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("refund_status", ["full", "over"])
async def test_prepare_payment_rejects_refunded_paid_order(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
    refund_status: str,
) -> None:
    """已支付且已全额退款的订单不得重新进入支付准备入口。"""
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-refunded-paid-prepare")
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    await order_service.reconcile_refund_from_query(
        {
            "mchid": "mch-refunded-paid-prepare",
            "out_trade_no": order_id,
            "transaction_id": f"wx-{order_id}",
            "out_refund_no": "R-PAID-PREPARE",
            "refund_id": "refund-paid-prepare",
            "refund_status": "SUCCESS",
            "success_time": "2026-09-25T12:00:00+08:00",
            "amount": {
                "total": 5000,
                "refund": 5000,
                "payer_total": 5000,
                "payer_refund": 5000,
            },
        },
        payer_total_fen=5000,
    )
    order_repo = OrderRepo(db)
    order = await order_repo.get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    payment["refundStatus"] = refund_status
    await order_repo.update_payment(
        order_id, dumps_payment(payment), "2026-09-25 12:00:00"
    )

    runtime = order_service._payment_service._payment_service
    prepay_calls: list[dict] = []

    async def fake_create_jsapi_prepay(**kwargs: object) -> WechatPayPrepayResult:
        prepay_calls.append(kwargs)
        return WechatPayPrepayResult(
            prepay_id=f"wx-prepay-{order_id}", appid="wx-app-id"
        )

    monkeypatch.setattr(runtime._wechat_pay_service, "is_ready", lambda: True)
    monkeypatch.setattr(
        runtime._wechat_pay_service,
        "create_jsapi_prepay",
        fake_create_jsapi_prepay,
    )

    with pytest.raises(ValueError, match="订单已退款，不能继续支付"):
        await order_service.prepare_payment(order_id, user_id=USER_ID)

    assert prepay_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("refund_status", ["full", "over"])
async def test_confirm_mock_payment_rejects_refunded_partial_order(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    refund_status: str,
) -> None:
    """退款终态组合支付订单不得被 mock 支付重新置为已支付。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    order_repo = OrderRepo(db)
    order = await order_repo.get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    payment["refundStatus"] = refund_status
    await order_repo.update_payment(
        order_id, dumps_payment(payment), "2026-08-20 19:00"
    )

    with pytest.raises(ValueError, match="订单已退款，不能确认支付"):
        await order_service.confirm_mock_payment(order_id, user_id=USER_ID)

    latest = await order_repo.get_order(order_id)
    assert latest is not None
    assert loads_payment(latest.payment)["status"] == "partial"


@pytest.mark.asyncio
@pytest.mark.parametrize("refund_status", ["full", "over"])
async def test_refunded_partial_order_balance_entry_is_rejected_without_deduct(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    refund_status: str,
) -> None:
    """真实组合支付中间态已有部分余额时，退款终态不得再次扣余额。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    order_repo = OrderRepo(db)
    order = await order_repo.get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    payment["refundStatus"] = refund_status
    await order_repo.update_payment(
        order_id, dumps_payment(payment), "2026-08-20 19:00"
    )

    with pytest.raises(ValueError, match="订单已部分支付"):
        await stored_value_service.pay_order_with_balance(order_id, user_id=USER_ID)

    assert await _balance_fen(db) == 98_000
    ledger = await _ledger_rows(db)
    assert len(ledger) == 1
    assert ledger[0]["biz_type"] == "order_pay"
    latest = await order_repo.get_order(order_id)
    assert latest is not None
    assert loads_payment(latest.payment)["status"] == "partial"


@pytest.mark.asyncio
@pytest.mark.parametrize("refund_status", ["full", "over"])
async def test_refunded_partial_order_combined_prepare_is_rejected_without_prepay(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
    refund_status: str,
) -> None:
    """真实组合支付中间态已有部分余额时，退款终态不得再发起组合支付。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    order_repo = OrderRepo(db)
    order = await order_repo.get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    payment["refundStatus"] = refund_status
    await order_repo.update_payment(
        order_id, dumps_payment(payment), "2026-08-20 19:00"
    )

    payment_service = stored_value_service.payment_service
    prepay_calls: list[dict] = []

    async def fake_create_jsapi_prepay(**kwargs: object) -> WechatPayPrepayResult:
        prepay_calls.append(kwargs)
        return WechatPayPrepayResult(
            prepay_id=f"wx-prepay-{order_id}", appid="wx-app-id"
        )

    monkeypatch.setattr(payment_service._wechat_pay_service, "is_ready", lambda: True)
    monkeypatch.setattr(
        payment_service._wechat_pay_service,
        "create_jsapi_prepay",
        fake_create_jsapi_prepay,
    )

    with pytest.raises(ValueError, match="订单已部分支付"):
        await stored_value_service.prepare_combined_payment(
            order_id, user_id=USER_ID, balance_fen=1000
        )

    assert prepay_calls == []
    assert await _balance_fen(db) == 98_000
    latest = await order_repo.get_order(order_id)
    assert latest is not None
    assert loads_payment(latest.payment)["status"] == "partial"


@pytest.mark.asyncio
@pytest.mark.parametrize("close_method", ["cancel", "expire"])
async def test_refunded_partial_order_close_does_not_duplicate_balance_refund(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    close_method: str,
) -> None:
    """退款已入账后关闭订单只能幂等重放余额退款，不得二次入账。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    order_repo = OrderRepo(db)
    order = await order_repo.get_order(order_id)
    assert order is not None
    payment = loads_payment(order.payment)
    payment["refundStatus"] = "full"
    refunded_order = await order_repo.update_payment(
        order_id, dumps_payment(payment), "2026-08-20 19:00"
    )
    assert refunded_order is not None
    await stored_value_service.refund_order_balance(refunded_order)
    assert await _balance_fen(db) == 100_000

    if close_method == "cancel":
        result = await order_service.cancel_user_order(order_id, user_id=USER_ID)
    else:
        result = await order_service.expire_unpaid_order(order_id)

    assert result["status"] == "cancelled"
    assert await _balance_fen(db) == 100_000
    ledger = await _ledger_rows(db)
    assert [row["biz_type"] for row in ledger] == ["order_pay", "order_refund"]
    assert ledger[1]["amount_fen"] == 2000


@pytest.mark.asyncio
async def test_refunded_paid_order_rejects_repeat_asset_settlement(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已全额退款订单再次确认支付不得重写已清零的积分结算快照。"""
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-refunded-reentry")
    await _seed_member(db, balance_fen=100_000)
    mock_order_id = await _create_order(order_service, price_fen=5000)
    balance_order_id = await _create_order(order_service, price_fen=5000)

    notifier = WechatPaymentNotificationService(order_repo=OrderRepo(db))
    for order_id in (mock_order_id, balance_order_id):
        await notifier.mark_paid(
            order_id,
            paid_at="2026-09-25 12:00:00",
            transaction_id=f"wx-{order_id}",
        )
    assert await _points_balance(db) == 100

    for order_id, refund_no in (
        (mock_order_id, "R-MOCK-REENTRY"),
        (balance_order_id, "R-BALANCE-REENTRY"),
    ):
        await order_service.reconcile_refund_from_query(
            {
                "mchid": "mch-refunded-reentry",
                "out_trade_no": order_id,
                "transaction_id": f"wx-{order_id}",
                "out_refund_no": refund_no,
                "refund_id": f"refund-{refund_no}",
                "refund_status": "SUCCESS",
                "success_time": "2026-09-25T12:00:00+08:00",
                "amount": {
                    "total": 5000,
                    "refund": 5000,
                    "payer_total": 5000,
                    "payer_refund": 5000,
                },
            },
            payer_total_fen=5000,
        )

    assert await _points_balance(db) == 0
    for order_id in (mock_order_id, balance_order_id):
        payment = loads_payment((await OrderRepo(db).get_order(order_id)).payment)
        assert payment["refundStatus"] == "full"
        assert payment["pointsAwarded"] == 0

    with pytest.raises(ValueError, match="订单已退款，不能确认支付"):
        await order_service.confirm_mock_payment(mock_order_id, user_id=USER_ID)
    with pytest.raises(ValueError, match="订单已退款，不能使用余额支付"):
        await stored_value_service.pay_order_with_balance(
            balance_order_id, user_id=USER_ID
        )

    assert await _points_balance(db) == 0
    for order_id in (mock_order_id, balance_order_id):
        payment = loads_payment((await OrderRepo(db).get_order(order_id)).payment)
        assert payment["pointsAwarded"] == 0


@pytest.mark.asyncio
async def test_partially_refunded_paid_order_reentry_does_not_repeat_asset_settlement(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """部分退款事实下重入已支付入口不得重复核销、发放或记账。"""
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-partial-reentry")
    await _seed_member(db, balance_fen=100_000)
    await _seed_coupon(db)
    order_repo = OrderRepo(db)
    coupon_service = CouponService(
        order_repo=order_repo,
        customer_repo=CustomerMasterRepo(db),
        template_repo=CouponTemplateRepo(db),
        inventory_repo=CouponInventoryRepo(db),
    )

    mock_order_id = await _create_order(order_service, price_fen=5000)
    await coupon_service.apply_coupon(
        mock_order_id, user_id=USER_ID, coupon_id="coupon-late-cancel"
    )
    await order_service.confirm_mock_payment(mock_order_id, user_id=USER_ID)

    balance_order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        balance_order_id, user_id=USER_ID, balance_fen=2000
    )
    await order_service.confirm_mock_payment(balance_order_id, user_id=USER_ID)

    await order_service.reconcile_refund_from_query(
        {
            "mchid": "mch-partial-reentry",
            "out_trade_no": mock_order_id,
            "transaction_id": f"wx-partial-{mock_order_id}",
            "out_refund_no": "R-PARTIAL-MOCK-REENTRY",
            "refund_id": "refund-partial-mock-reentry",
            "refund_status": "SUCCESS",
            "success_time": "2026-09-25T12:05:00+08:00",
            "amount": {
                "total": 4500,
                "refund": 1000,
                "payer_total": 4500,
                "payer_refund": 1000,
            },
        },
        payer_total_fen=4500,
    )
    await order_service.reconcile_refund_from_query(
        {
            "mchid": "mch-partial-reentry",
            "out_trade_no": balance_order_id,
            "transaction_id": f"wx-partial-{balance_order_id}",
            "out_refund_no": "R-PARTIAL-BALANCE-REENTRY",
            "refund_id": "refund-partial-balance-reentry",
            "refund_status": "SUCCESS",
            "success_time": "2026-09-25T12:05:00+08:00",
            "amount": {
                "total": 3000,
                "refund": 1000,
                "payer_total": 3000,
                "payer_refund": 1000,
            },
        },
        payer_total_fen=3000,
    )

    async def snapshot() -> dict[str, int]:
        balance_ledger = await db.execute_fetchall(
            "SELECT COUNT(*) AS count FROM balance_ledger WHERE mobile = ?",
            (MOBILE,),
        )
        points_ledger = await db.execute_fetchall(
            "SELECT COUNT(*) AS count FROM points_ledger WHERE mobile = ?",
            (MOBILE,),
        )
        payment_transactions = await db.execute_fetchall(
            "SELECT COUNT(*) AS count FROM payment_transactions"
        )
        order_events = await db.execute_fetchall(
            "SELECT COUNT(*) AS count FROM order_events WHERE order_id IN (?, ?)",
            (mock_order_id, balance_order_id),
        )
        coupon_consumes = await db.execute_fetchall(
            "SELECT COUNT(*) AS count FROM coupon_inventory "
            "WHERE coupon_id = ? AND status = 'CONSUME'",
            ("coupon-late-cancel",),
        )
        return {
            "balance_fen": await _balance_fen(db),
            "points": await _points_balance(db),
            "balance_ledger": int(balance_ledger[0]["count"]),
            "points_ledger": int(points_ledger[0]["count"]),
            "payment_transactions": int(payment_transactions[0]["count"]),
            "order_events": int(order_events[0]["count"]),
            "coupon_consumes": int(coupon_consumes[0]["count"]),
        }

    before = await snapshot()
    mock_again = await order_service.confirm_mock_payment(
        mock_order_id, user_id=USER_ID
    )
    balance_again = await stored_value_service.pay_order_with_balance(
        balance_order_id, user_id=USER_ID
    )
    after = await snapshot()

    assert mock_again["paymentStatus"] == "paid"
    assert balance_again["paymentStatus"] == "paid"
    assert after == before
    assert after["coupon_consumes"] == 1
    assert (
        loads_payment((await order_repo.get_order(mock_order_id)).payment)[
            "refundStatus"
        ]
        == "partial"
    )
    assert (
        loads_payment((await order_repo.get_order(balance_order_id)).payment)[
            "refundStatus"
        ]
        == "partial"
    )


@pytest.mark.asyncio
async def test_combined_payment_wechat_notify_uses_remainder_amount(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """组合支付差额走微信时，通知金额应按差额校验而非订单总额。"""
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-stored")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-stored")
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    notifier = WechatPaymentNotificationService(order_repo=OrderRepo(db))
    base = {
        "out_trade_no": order_id,
        "mchid": "mch-stored",
        "appid": "appid-stored",
        "trade_state": "SUCCESS",
        "success_time": "2026-08-15T12:00:00+08:00",
        "transaction_id": "4200000000202608121234567890",
    }
    # B3.5（评审问题 4）：币种取 amount.currency（顶层无 currency），字段按真实 v3 报文
    await notifier.validate_transaction(
        {**base, "amount": {"total": 3000, "currency": "CNY"}}
    )
    with pytest.raises(ValueError, match="金额不匹配"):
        await notifier.validate_transaction(
            {**base, "amount": {"total": 5000, "currency": "CNY"}}
        )
    with pytest.raises(ValueError, match="币种"):
        await notifier.validate_transaction(
            {**base, "amount": {"total": 3000, "currency": "USD"}}
        )


@pytest.mark.asyncio
async def test_combined_payment_query_recovery_uses_remainder_and_settles_once(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """组合支付查询恢复应按差额确认订单，重复查询不重复扣款或落事件。"""
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-stored-query")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-stored-query")
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    query = {
        "out_trade_no": order_id,
        "mchid": "mch-stored-query",
        "appid": "appid-stored-query",
        "trade_state": "SUCCESS",
        "amount": {"total": 3000, "currency": "CNY"},
        "transaction_id": "4200000000202609251234567890",
        "success_time": "2026-09-25T12:00:00+08:00",
    }

    first = await order_service.reconcile_pay_from_query(query)
    second = await order_service.reconcile_pay_from_query(query)

    assert first["paymentStatus"] == "paid"
    assert first["paymentMethod"] == "combined"
    assert second["paymentStatus"] == "paid"
    assert await _balance_fen(db) == 98_000
    ledger = await _ledger_rows(db)
    assert len(ledger) == 1
    assert ledger[0]["biz_type"] == "order_pay"
    assert ledger[0]["amount_fen"] == -2000
    paid_events = await db.execute_fetchall(
        "SELECT status FROM order_events WHERE order_id = ? AND status = 'paid'",
        (order_id,),
    )
    assert len(paid_events) == 1
