"""MiniApp 核心闭环 r34：普通微信预支付后真实取消候选复核。"""

import json

import aiosqlite
import pytest

from app.config import settings
from app.models.order import Order, OrderStatus
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.points_ledger_repo import PointsLedgerRepo
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

ORDER_ID = "order_wechat_cancel_001"
USER_ID = "wx_wechat_cancel_001"
OPENID = "wechat_cancel_001"
MOBILE = "13800003034"
ORDER_AMOUNT_FEN = 10_000
INITIAL_BALANCE_FEN = 20_000
INITIAL_POINTS = 1_000
TRANSACTION_ID = "4200000000202609251234567892"
EVENT_ID = "EV-wechat-cancel-001"
RETRY_EVENT_ID = "EV-wechat-cancel-retry-001"


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
            "nonceStr": "nonce-r34",
            "package": f"prepay_id={prepay_id}",
            "signType": "RSA",
            "paySign": "signed-r34",
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
        return now_text()

    def sign_with_rsa(self, message: str) -> str:
        return f"signature:{message}"


async def _seed_order_and_member(connection: aiosqlite.Connection) -> None:
    """写入普通待支付微信订单和具备资产的本地会员。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '微信取消复核会员', 'high', 1)",
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
        "VALUES (?, ?, ?)",
        (MOBILE, INITIAL_BALANCE_FEN, INITIAL_POINTS),
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
                        "product_id": "p_wechat_cancel",
                        "title": "微信取消复核蛋糕",
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
    await connection.commit()


def _build_cancellation_service(
    connection: aiosqlite.Connection,
    order_repo: OrderRepo,
    event_repo: OrderEventRepo,
) -> OrderCancellationService:
    """按生产依赖装配用户取消服务。"""
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(connection),
        ledger_repo=BalanceLedgerRepo(connection),
        customer_repo=CustomerMasterRepo(connection),
    )
    payment_service = StoredValueOrderPaymentService(
        order_repo=order_repo,
        member_service=member_service,
    )
    return OrderCancellationService(
        order_repo=order_repo,
        inventory_service=OrderInventoryService(
            product_repo=LegacyOrderProductRepo(connection),
            inventory_repo=LegacyOrderInventoryRepo(connection),
        ),
        timeline_service=OrderTimelineService(
            serialization_service=OrderSerializationService(),
            event_repo=event_repo,
        ),
        stored_value_service=StoredValueService(
            member_service=member_service,
            payment_service=payment_service,
        ),
    )


@pytest.mark.asyncio
async def test_real_wechat_cancel_and_late_notify_record_refund_once(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """普通微信预支付取消后，迟到到账应幂等记录且不得误退资产。"""
    await _seed_order_and_member(db)
    transaction = {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": "mch-r34",
        "appid": "appid-r34",
        "amount": {"total": ORDER_AMOUNT_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T12:00:00+08:00",
    }
    integration = _FakeWechatPayIntegration(transaction)
    order_repo = OrderRepo(db)
    event_repo = OrderEventRepo(db)
    runtime = OrderPaymentRuntimeService(order_repo, integration, event_repo)
    cancellation = _build_cancellation_service(db, order_repo, event_repo)
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-r34")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-r34")

    session = await runtime.prepare_payment(ORDER_ID, user_id=USER_ID)
    await db.commit()
    first_cancel = await cancellation.cancel_user_order(ORDER_ID, user_id=USER_ID)
    await db.commit()
    cancelled_order = await order_repo.get_order(ORDER_ID)
    repeated_cancel = await cancellation.cancel_user_order(ORDER_ID, user_id=USER_ID)
    await db.commit()

    raw_body = json.dumps(
        {
            "id": EVENT_ID,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {},
        }
    ).encode("utf-8")
    late_notify = await runtime.handle_wechat_payment_notify(
        raw_body=raw_body,
        headers={},
    )
    duplicate_notify = await runtime.handle_wechat_payment_notify(
        raw_body=raw_body,
        headers={},
    )
    retry_raw_body = json.dumps(
        {
            "id": RETRY_EVENT_ID,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {},
        }
    ).encode("utf-8")
    retry_notify = await runtime.handle_wechat_payment_notify(
        raw_body=retry_raw_body,
        headers={},
    )
    repeated_cancel_after_notify = await cancellation.cancel_user_order(
        ORDER_ID,
        user_id=USER_ID,
    )

    order = await order_repo.get_order(ORDER_ID)
    events = await event_repo.list_by_order(ORDER_ID)
    transactions = await db.execute_fetchall(
        "SELECT transaction_id FROM payment_transactions WHERE order_id = ?",
        (ORDER_ID,),
    )
    balance_rows = await db.execute_fetchall(
        "SELECT stored_value_fen, points FROM member_balance WHERE mobile = ?",
        (MOBILE,),
    )
    balance_ledger = await db.execute_fetchall(
        "SELECT unique_id FROM balance_ledger WHERE biz_id = ?",
        (ORDER_ID,),
    )
    points_ledger = await PointsLedgerRepo(db).list_by_mobile(MOBILE)
    inbox_rows = await db.execute_fetchall(
        "SELECT status, attempt_count FROM inbox_events WHERE queue_name = ?",
        ("wechat_pay_notify",),
    )

    assert session.mode == "wechat"
    assert integration.prepay_amounts == [ORDER_AMOUNT_FEN]
    assert cancelled_order is not None
    cancelled_payment = json.loads(cancelled_order.payment)
    assert str(cancelled_order.status) == OrderStatus.CANCELLED.value
    assert str(cancelled_payment["status"]) == "unpaid"
    assert int(cancelled_payment["externalPaidFen"]) == ORDER_AMOUNT_FEN
    assert int(cancelled_payment["wechatPrepayFen"]) == ORDER_AMOUNT_FEN
    assert str(first_cancel["status"]) == OrderStatus.CANCELLED.value
    assert str(repeated_cancel["status"]) == OrderStatus.CANCELLED.value
    assert str(repeated_cancel_after_notify["status"]) == OrderStatus.CANCELLED.value
    assert str(late_notify["status"]) == OrderStatus.CANCELLED.value
    assert str(late_notify["paymentStatus"]) == "paid"
    assert str(late_notify["paymentRefundStatus"]) == "pending"
    assert int(late_notify["paymentRefundAmountFen"]) == ORDER_AMOUNT_FEN
    assert duplicate_notify == {"duplicate": True}
    assert str(retry_notify["status"]) == OrderStatus.CANCELLED.value
    assert str(retry_notify["paymentStatus"]) == "paid"
    assert str(retry_notify["paymentRefundStatus"]) == "pending"

    assert order is not None
    assert str(order.status) == OrderStatus.CANCELLED.value
    payment = json.loads(order.payment)
    assert str(payment["status"]) == "paid"
    assert str(payment["method"]) == "wechat"
    assert str(payment["transactionId"]) == TRANSACTION_ID
    assert int(payment["externalPaidFen"]) == ORDER_AMOUNT_FEN
    assert int(payment["wechatPrepayFen"]) == ORDER_AMOUNT_FEN
    assert str(payment["refundStatus"]) == "pending"
    assert int(payment["refundAmountFen"]) == ORDER_AMOUNT_FEN

    assert [str(event.status) for event in events] == [
        OrderStatus.CANCELLED.value,
        "paid",
    ]
    assert [str(row["transaction_id"]) for row in transactions] == [TRANSACTION_ID]
    assert [
        (int(row["stored_value_fen"]), int(row["points"])) for row in balance_rows
    ] == [(INITIAL_BALANCE_FEN, INITIAL_POINTS)]
    assert balance_ledger == []
    assert [entry for entry in points_ledger if entry.biz_id == ORDER_ID] == []
    assert sorted(
        (str(row["status"]), int(row["attempt_count"])) for row in inbox_rows
    ) == [("processed", 1), ("processed", 1)]
