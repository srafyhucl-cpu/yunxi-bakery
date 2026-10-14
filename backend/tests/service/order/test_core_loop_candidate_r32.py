"""MiniApp 核心闭环 r32：微信预支付金额锁定候选复现。"""

import json

import aiosqlite
import pytest

from app.config import settings
from app.models.coupon import CouponTemplate, CouponType
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.models.order import Order, OrderStatus
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.coupon import CouponService
from app.service.coupon.inventory import CouponInventoryService
from app.service.integrations.wechat_pay import WechatPayPrepayResult
from app.service.order.cancellation import OrderCancellationService
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.order.serialization import OrderSerializationService
from app.service.order.timeline import OrderTimelineService
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
    StoredValueService,
)
from tests.helpers.legacy_order_catalog import (
    LegacyOrderInventoryRepo,
    LegacyOrderProductRepo,
)

ORDER_ID = "order_wechat_prepay_lock_001"
USER_ID = "wx_wechat_prepay_lock_001"
OPENID = "wechat_prepay_lock_001"
MOBILE = "13800003032"
ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 500
COUPON_ID = "coupon_wechat_prepay_lock_001"
TRANSACTION_ID = "4200000000202609251234567890"
EVENT_ID = "EV-wechat-prepay-lock-001"
INITIAL_BALANCE_FEN = 20_000


class _FakeWechatPayIntegration:
    """记录预支付金额并返回确定性的本地微信结果。"""

    def __init__(self, transaction: dict) -> None:
        self.transaction = transaction
        self.prepay_amounts: list[int] = []

    def is_ready(self) -> bool:
        return True

    async def create_jsapi_prepay(
        self,
        *,
        order_id: str,
        total_fen: int,
        description: str,
        payer_openid: str,
    ) -> WechatPayPrepayResult:
        self.prepay_amounts.append(total_fen)
        return WechatPayPrepayResult(
            prepay_id=f"prepay-{order_id}-{total_fen}",
            appid=settings.WECHAT_MINIAPP_APP_ID,
        )

    def build_payment_params(
        self,
        prepay_id: str,
        *,
        signer,
    ) -> dict:
        return {
            "timeStamp": "1789756800",
            "nonceStr": "nonce-r32",
            "package": f"prepay_id={prepay_id}",
            "signType": "RSA",
            "paySign": "signed-r32",
        }

    def verify_notify_signature(
        self,
        raw_body: bytes,
        headers: dict[str, str],
        *,
        now_seconds: int | None = None,
    ) -> bool:
        return True

    def decrypt_notify_resource(self, resource: dict) -> dict:
        return dict(self.transaction)

    def format_success_time(self, value: str) -> str:
        return "2026-09-25 12:00:00"

    def sign_with_rsa(self, message: str) -> str:
        return f"signature:{message}"


async def _seed_order_member_and_coupon(connection: aiosqlite.Connection) -> None:
    """写入待支付订单、会员身份和一张可用券。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '微信预支付锁会员', 'high', 1)",
        (f"cm_{ORDER_ID}", MOBILE),
    )
    await connection.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (f"cil_{ORDER_ID}", f"cm_{ORDER_ID}", OPENID, OPENID),
    )
    await connection.execute(
        "INSERT INTO member_balance (mobile, stored_value_fen, points) "
        "VALUES (?, ?, 0)",
        (MOBILE, INITIAL_BALANCE_FEN),
    )
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id, status) "
        "VALUES (?, 'miniapp', ?, 'active')",
        (f"session_{ORDER_ID}", USER_ID),
    )
    await OrderRepo(connection).create_order(
        Order(
            id=ORDER_ID,
            session_id=f"session_{ORDER_ID}",
            channel="miniapp",
            user_id=USER_ID,
            products=json.dumps(
                [
                    {
                        "product_id": "p_wechat_prepay_lock",
                        "title": "微信预支付金额锁定蛋糕",
                        "price_fen": ORDER_AMOUNT_FEN,
                        "quantity": 1,
                        "inventory_reserved": False,
                    }
                ],
                ensure_ascii=False,
            ),
            total_amount=ORDER_AMOUNT_FEN / 100,
            delivery=json.dumps({}, ensure_ascii=False),
            payment=json.dumps(build_initial_payment(now_text()), ensure_ascii=False),
            status=OrderStatus.PENDING,
            remark="",
            created_at=now_text(),
            updated_at=now_text(),
        )
    )
    template_id = "cg_wechat_prepay_lock_001"
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=template_id,
            name="微信预支付锁测试券",
            coupon_type=CouponType.FULL_REDUCTION,
            threshold_fen=3_000,
            value_fen=COUPON_FEN,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await CouponInventoryRepo(connection).insert(
        CouponInventoryEntry(
            coupon_id=COUPON_ID,
            status=CouponStatus.TAKE,
            mobile=MOBILE,
            coupon_group_id=template_id,
            title="微信预支付锁测试券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id=template_id,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()


@pytest.mark.asyncio
async def test_wechat_prepay_locks_asset_snapshot_before_coupon_application(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """微信预支付返回后不得再改写该会话对应的资产金额快照。"""
    await _seed_order_member_and_coupon(db)
    transaction = {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": "mch-r32",
        "appid": "appid-r32",
        "amount": {"total": ORDER_AMOUNT_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T12:00:00+08:00",
    }
    integration = _FakeWechatPayIntegration(transaction)
    runtime = OrderPaymentRuntimeService(OrderRepo(db), integration)
    coupon_service = CouponService(
        template_repo=CouponTemplateRepo(db),
        inventory_repo=CouponInventoryRepo(db),
        customer_repo=CustomerMasterRepo(db),
        order_repo=OrderRepo(db),
        inventory_service=CouponInventoryService(db),
    )
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-r32")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-r32")

    session = await runtime.prepare_payment(ORDER_ID, user_id=USER_ID)
    await db.commit()

    coupon_rejected = False
    coupon_error = ""
    try:
        await coupon_service.apply_coupon(
            ORDER_ID,
            user_id=USER_ID,
            coupon_id=COUPON_ID,
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        coupon_rejected = True
        coupon_error = str(exc)

    if not coupon_rejected:
        raw_body = json.dumps(
            {"id": EVENT_ID, "event_type": "TRANSACTION.SUCCESS", "resource": {}}
        ).encode("utf-8")
        with pytest.raises(ValueError, match="金额不匹配"):
            await runtime.handle_wechat_payment_notify(
                raw_body=raw_body,
                headers={},
            )
        bad_state = await db.execute_fetchall(
            "SELECT status, attempt_count, last_error FROM inbox_events "
            "WHERE message_key = ?",
            (f"wechat_pay_notify:{EVENT_ID}",),
        )
        transactions = await db.execute_fetchall(
            "SELECT transaction_id FROM payment_transactions WHERE order_id = ?",
            (ORDER_ID,),
        )
        assert len(bad_state) == 1
        assert str(bad_state[0]["status"]) == "failed"
        assert int(bad_state[0]["attempt_count"]) == 1
        assert "金额不匹配" in str(bad_state[0]["last_error"])
        assert transactions == []

    order = await OrderRepo(db).get_order(ORDER_ID)
    coupon_rows = await db.execute_fetchall(
        "SELECT status, order_no FROM coupon_inventory WHERE coupon_id = ?",
        (COUPON_ID,),
    )
    assert integration.prepay_amounts == [ORDER_AMOUNT_FEN]
    assert session.mode == "wechat"
    assert session.payment_status == "unpaid"
    assert order is not None
    payment = json.loads(order.payment)
    assert str(order.status) == OrderStatus.PENDING.value
    assert str(payment["status"]) == "unpaid"
    assert int(payment.get("externalPaidFen", 0)) == ORDER_AMOUNT_FEN
    assert int(payment.get("wechatPrepayFen", 0)) == ORDER_AMOUNT_FEN
    assert len(coupon_rows) == 1
    assert str(coupon_rows[0]["status"]) == CouponStatus.TAKE
    assert str(coupon_rows[0]["order_no"] or "") == ""
    assert coupon_rejected, f"预支付后优惠券仍被接受：{coupon_error or coupon_rows}"
    if coupon_rejected:
        paid = await runtime.handle_wechat_payment_notify(
            raw_body=json.dumps(
                {
                    "id": EVENT_ID,
                    "event_type": "TRANSACTION.SUCCESS",
                    "resource": {},
                }
            ).encode("utf-8"),
            headers={},
        )
        transactions = await db.execute_fetchall(
            "SELECT transaction_id FROM payment_transactions WHERE order_id = ?",
            (ORDER_ID,),
        )
        assert str(paid["paymentStatus"]) == "paid"
        assert str(paid["paymentMethod"]) == "wechat"
        assert [(row["transaction_id"]) for row in transactions] == [TRANSACTION_ID]


@pytest.mark.asyncio
@pytest.mark.parametrize("payment_mode", ["balance", "combined"])
async def test_wechat_prepay_blocks_later_local_payment_without_asset_deduction(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
    payment_mode: str,
) -> None:
    """微信会话锁定后不得再扣余额或重新生成另一条支付腿。"""
    await _seed_order_member_and_coupon(db)
    integration = _FakeWechatPayIntegration({})
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    local_payment = StoredValueOrderPaymentService(
        order_repo=OrderRepo(db),
        member_service=member_service,
        wechat_pay_service=integration,
    )
    runtime = OrderPaymentRuntimeService(OrderRepo(db), integration)
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-r32")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-r32")

    await runtime.prepare_payment(ORDER_ID, user_id=USER_ID)
    await db.commit()

    with pytest.raises(ValueError, match="已发起微信支付"):
        if payment_mode == "balance":
            await local_payment.pay_order_with_balance(ORDER_ID, user_id=USER_ID)
        else:
            await local_payment.prepare_combined_payment(
                ORDER_ID,
                user_id=USER_ID,
                balance_fen=2_000,
            )

    order = await OrderRepo(db).get_order(ORDER_ID)
    balance_rows = await db.execute_fetchall(
        "SELECT stored_value_fen FROM member_balance WHERE mobile = ?",
        (MOBILE,),
    )
    ledger_rows = await db.execute_fetchall(
        "SELECT unique_id FROM balance_ledger WHERE biz_id = ?",
        (ORDER_ID,),
    )
    assert integration.prepay_amounts == [ORDER_AMOUNT_FEN]
    assert order is not None
    payment = json.loads(order.payment)
    assert str(payment["status"]) == "unpaid"
    assert int(payment["externalPaidFen"]) == ORDER_AMOUNT_FEN
    assert int(payment["wechatPrepayFen"]) == ORDER_AMOUNT_FEN
    assert int(balance_rows[0]["stored_value_fen"]) == INITIAL_BALANCE_FEN
    assert ledger_rows == []


@pytest.mark.asyncio
async def test_real_wechat_combined_payment_deducts_balance_and_locks_remainder(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实微信组合支付应保留唯一余额腿并锁定微信尾款。"""
    await _seed_order_member_and_coupon(db)
    integration = _FakeWechatPayIntegration({})
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    local_payment = StoredValueOrderPaymentService(
        order_repo=OrderRepo(db),
        member_service=member_service,
        wechat_pay_service=integration,
    )
    runtime = OrderPaymentRuntimeService(OrderRepo(db), integration)
    balance_fen = 2_000
    remain_fen = ORDER_AMOUNT_FEN - balance_fen
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)

    combined = await local_payment.prepare_combined_payment(
        ORDER_ID,
        user_id=USER_ID,
        balance_fen=balance_fen,
    )
    await db.commit()

    with pytest.raises(ValueError, match="已发起微信支付"):
        await local_payment.pay_order_with_balance(ORDER_ID, user_id=USER_ID)
    with pytest.raises(ValueError, match="已发起微信支付"):
        await runtime.confirm_mock_payment(ORDER_ID, user_id=USER_ID)

    order = await OrderRepo(db).get_order(ORDER_ID)
    balance_rows = await db.execute_fetchall(
        "SELECT stored_value_fen FROM member_balance WHERE mobile = ?",
        (MOBILE,),
    )
    ledger_rows = await db.execute_fetchall(
        "SELECT unique_id, amount_fen FROM balance_ledger WHERE biz_id = ?",
        (ORDER_ID,),
    )
    assert integration.prepay_amounts == [remain_fen]
    assert combined["payment"]["status"] == "partial"
    assert int(combined["payment"]["balanceFen"]) == balance_fen
    assert int(combined["payment"]["remainFen"]) == remain_fen
    assert combined["remainderPayment"]["mode"] == "wechat"
    assert order is not None
    payment = json.loads(order.payment)
    assert str(payment["status"]) == "partial"
    assert int(payment["balanceFen"]) == balance_fen
    assert int(payment["remainFen"]) == remain_fen
    assert int(payment["externalPaidFen"]) == remain_fen
    assert int(payment["wechatPrepayFen"]) == remain_fen
    assert int(balance_rows[0]["stored_value_fen"]) == (
        INITIAL_BALANCE_FEN - balance_fen
    )
    assert len(ledger_rows) == 1
    assert str(ledger_rows[0]["unique_id"]) == f"combined_pay:{ORDER_ID}"
    assert int(ledger_rows[0]["amount_fen"]) == -balance_fen


@pytest.mark.asyncio
async def test_real_wechat_combined_payment_late_success_refunds_external_leg_once(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """组合支付取消后迟到到账应按锁定尾款退款且不重复退余额。"""
    await _seed_order_member_and_coupon(db)
    balance_fen = 2_000
    remain_fen = ORDER_AMOUNT_FEN - balance_fen
    transaction = {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": "mch-r32",
        "appid": "appid-r32",
        "amount": {"total": remain_fen, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T12:00:00+08:00",
    }
    integration = _FakeWechatPayIntegration(transaction)
    order_repo = OrderRepo(db)
    event_repo = OrderEventRepo(db)
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    local_payment = StoredValueOrderPaymentService(
        order_repo=order_repo,
        member_service=member_service,
        wechat_pay_service=integration,
    )
    stored_value_service = StoredValueService(
        member_service=member_service,
        payment_service=local_payment,
    )
    runtime = OrderPaymentRuntimeService(order_repo, integration, event_repo)
    cancellation = OrderCancellationService(
        order_repo=order_repo,
        inventory_service=OrderInventoryService(
            product_repo=LegacyOrderProductRepo(db),
            inventory_repo=LegacyOrderInventoryRepo(db),
        ),
        timeline_service=OrderTimelineService(
            serialization_service=OrderSerializationService(),
            event_repo=event_repo,
        ),
        stored_value_service=stored_value_service,
    )
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-r32")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-r32")

    await local_payment.prepare_combined_payment(
        ORDER_ID,
        user_id=USER_ID,
        balance_fen=balance_fen,
    )
    cancelled = await cancellation.cancel_user_order(ORDER_ID, user_id=USER_ID)
    result = await runtime.handle_wechat_payment_notify(
        raw_body=json.dumps(
            {
                "id": EVENT_ID,
                "event_type": "TRANSACTION.SUCCESS",
                "resource": {},
            }
        ).encode("utf-8"),
        headers={},
    )

    assert str(cancelled["status"]) == OrderStatus.CANCELLED.value
    assert str(result["status"]) == OrderStatus.CANCELLED.value
    assert str(result["paymentStatus"]) == "paid"
    assert str(result["paymentRefundStatus"]) == "pending"
    assert int(result["paymentRefundAmountFen"]) == remain_fen
    order = await order_repo.get_order(ORDER_ID)
    balance_rows = await db.execute_fetchall(
        "SELECT stored_value_fen FROM member_balance WHERE mobile = ?",
        (MOBILE,),
    )
    ledger_rows = await db.execute_fetchall(
        "SELECT unique_id, amount_fen FROM balance_ledger WHERE biz_id = ? ORDER BY id",
        (ORDER_ID,),
    )
    transactions = await db.execute_fetchall(
        "SELECT transaction_id FROM payment_transactions WHERE order_id = ?",
        (ORDER_ID,),
    )
    assert integration.prepay_amounts == [remain_fen]
    assert order is not None
    payment = json.loads(order.payment)
    assert int(payment["externalPaidFen"]) == remain_fen
    assert int(payment["wechatPrepayFen"]) == remain_fen
    assert str(payment["transactionId"]) == TRANSACTION_ID
    assert int(balance_rows[0]["stored_value_fen"]) == INITIAL_BALANCE_FEN
    assert [str(row["unique_id"]) for row in ledger_rows] == [
        f"combined_pay:{ORDER_ID}",
        f"order_refund:{ORDER_ID}",
    ]
    assert [int(row["amount_fen"]) for row in ledger_rows] == [
        -balance_fen,
        balance_fen,
    ]
    assert [str(row["transaction_id"]) for row in transactions] == [TRANSACTION_ID]


@pytest.mark.asyncio
async def test_failed_wechat_prepay_keeps_amount_lock(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """外部结果不确定时不得解除本次微信支付金额锁。"""
    await _seed_order_member_and_coupon(db)
    integration = _FakeWechatPayIntegration({})

    async def fail_prepay(**_: object):
        raise TimeoutError("模拟微信预下单响应不确定")

    monkeypatch.setattr(integration, "create_jsapi_prepay", fail_prepay)
    runtime = OrderPaymentRuntimeService(OrderRepo(db), integration)

    with pytest.raises(TimeoutError, match="响应不确定"):
        await runtime.prepare_payment(ORDER_ID, user_id=USER_ID)

    order = await OrderRepo(db).get_order(ORDER_ID)
    assert order is not None
    payment = json.loads(order.payment)
    assert str(payment["status"]) == "unpaid"
    assert int(payment["externalPaidFen"]) == ORDER_AMOUNT_FEN
    assert int(payment["wechatPrepayFen"]) == ORDER_AMOUNT_FEN


@pytest.mark.asyncio
async def test_wechat_prepay_cannot_be_replaced_by_mock_payment(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实微信会话已发起后不得再用 mock 提前置为已支付。"""
    await _seed_order_member_and_coupon(db)
    integration = _FakeWechatPayIntegration({})
    runtime = OrderPaymentRuntimeService(OrderRepo(db), integration)
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)

    await runtime.prepare_payment(ORDER_ID, user_id=USER_ID)
    await db.commit()

    with pytest.raises(ValueError, match="已发起微信支付"):
        await runtime.confirm_mock_payment(ORDER_ID, user_id=USER_ID)

    order = await OrderRepo(db).get_order(ORDER_ID)
    transactions = await db.execute_fetchall(
        "SELECT transaction_id FROM payment_transactions WHERE order_id = ?",
        (ORDER_ID,),
    )
    assert order is not None
    payment = json.loads(order.payment)
    assert str(payment["status"]) == "unpaid"
    assert int(payment["wechatPrepayFen"]) == ORDER_AMOUNT_FEN
    assert transactions == []


@pytest.mark.asyncio
async def test_locked_wechat_prepay_late_payment_after_cancel_preserves_refund_fact(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已锁定的微信金额在订单取消后仍按原腿记录到账和待退款。"""
    await _seed_order_member_and_coupon(db)
    transaction = {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": "mch-r32",
        "appid": "appid-r32",
        "amount": {"total": ORDER_AMOUNT_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T12:00:00+08:00",
    }
    integration = _FakeWechatPayIntegration(transaction)
    runtime = OrderPaymentRuntimeService(OrderRepo(db), integration)
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-r32")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-r32")

    await runtime.prepare_payment(ORDER_ID, user_id=USER_ID)
    await db.execute(
        "UPDATE orders SET status = 'cancelled', updated_at = ? WHERE id = ?",
        ("2026-09-25 12:01:00", ORDER_ID),
    )
    await db.commit()

    result = await runtime.handle_wechat_payment_notify(
        raw_body=json.dumps(
            {
                "id": EVENT_ID,
                "event_type": "TRANSACTION.SUCCESS",
                "resource": {},
            }
        ).encode("utf-8"),
        headers={},
    )

    assert str(result["status"]) == OrderStatus.CANCELLED.value
    assert str(result["paymentStatus"]) == "paid"
    assert str(result["paymentRefundStatus"]) == "pending"
    assert int(result["paymentRefundAmountFen"]) == ORDER_AMOUNT_FEN
    order = await OrderRepo(db).get_order(ORDER_ID)
    assert order is not None
    payment = json.loads(order.payment)
    assert int(payment["externalPaidFen"]) == ORDER_AMOUNT_FEN
    assert int(payment["wechatPrepayFen"]) == ORDER_AMOUNT_FEN
    assert str(payment["transactionId"]) == TRANSACTION_ID
