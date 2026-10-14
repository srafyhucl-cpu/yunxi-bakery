"""MiniApp 核心闭环 r40：普通微信预支付与后台取消竞态。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.models.order import Order, OrderStatus
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.base import DatabaseHandle
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.integrations.wechat_pay import WechatPayPrepayResult
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.order.serialization import OrderSerializationService
from app.service.order.status_flow import OrderAdminStatusService
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

ORDER_ID = "order_admin_cancel_wechat_prepay_r40_001"
USER_ID = "wx_admin_cancel_wechat_prepay_r40_001"
OPENID = "admin_cancel_wechat_prepay_r40_001"
MOBILE = "13800003040"
ORDER_AMOUNT_FEN = 10_000
INITIAL_BALANCE_FEN = 20_000
INITIAL_POINTS = 1_000
EVENT_ID = "EV-admin-cancel-wechat-prepay-r40-001"
TRANSACTION_ID = "4200000000202609251234567893"


class _BlockingWechatPayIntegration:
    """记录预下单并按测试窗口等待后台取消提交。"""

    def __init__(self, *, block_prepay: bool) -> None:
        self.block_prepay = block_prepay
        self.prepay_started = asyncio.Event()
        self.admin_cancel_committed = asyncio.Event()
        self.prepay_amounts: list[int] = []
        self.transaction = {
            "out_trade_no": ORDER_ID,
            "trade_state": "SUCCESS",
            "mchid": "mch-r40",
            "appid": "appid-r40",
            "amount": {"total": ORDER_AMOUNT_FEN, "currency": "CNY"},
            "transaction_id": TRANSACTION_ID,
            "success_time": "2026-09-25T12:00:00+08:00",
        }

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
        """在外部调用边界记录金额，必要时阻塞到取消完成。"""
        self.prepay_amounts.append(total_fen)
        self.prepay_started.set()
        if self.block_prepay:
            await asyncio.wait_for(self.admin_cancel_committed.wait(), timeout=5)
        return WechatPayPrepayResult(
            prepay_id=f"prepay-{order_id}-{total_fen}",
            appid="appid-r40",
        )

    def build_payment_params(
        self,
        prepay_id: str,
        *,
        signer,
    ) -> dict:
        """返回可交给小程序端的合成微信支付参数。"""
        return {
            "timeStamp": "1789756800",
            "nonceStr": "nonce-r40",
            "package": f"prepay_id={prepay_id}",
            "signType": "RSA",
            "paySign": "signed-r40",
        }

    def verify_notify_signature(
        self,
        raw_body: bytes,
        headers: dict[str, str],
        *,
        now_seconds: int | None = None,
    ) -> bool:
        """接受测试签名的本地通知。"""
        return True

    def decrypt_notify_resource(self, resource: dict) -> dict:
        """返回固定的本地微信成功交易。"""
        return dict(self.transaction)

    def format_success_time(self, value: str) -> str:
        """返回测试使用的标准支付时间。"""
        return "2026-09-25 12:00:00"

    def sign_with_rsa(self, message: str) -> str:
        """返回确定性的本地签名占位。"""
        return f"signature:{message}"


def _build_member_service(handle: DatabaseHandle) -> MemberBalanceService:
    """为单个数据库连接构建真实会员余额服务。"""
    return MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )


def _build_admin_service(handle: DatabaseHandle) -> OrderAdminStatusService:
    """为单个数据库连接构建真实后台订单状态服务。"""
    member_service = _build_member_service(handle)
    payment_service = StoredValueOrderPaymentService(
        order_repo=OrderRepo(handle),
        member_service=member_service,
    )
    return OrderAdminStatusService(
        order_repo=OrderRepo(handle),
        inventory_service=OrderInventoryService(
            product_repo=LegacyOrderProductRepo(handle),
            inventory_repo=LegacyOrderInventoryRepo(handle),
        ),
        timeline_service=OrderTimelineService(
            serialization_service=OrderSerializationService(),
            event_repo=OrderEventRepo(handle),
        ),
        stored_value_service=StoredValueService(
            member_service=member_service,
            payment_service=payment_service,
        ),
    )


def _build_runtime(
    handle: DatabaseHandle,
    integration: _BlockingWechatPayIntegration,
) -> OrderPaymentRuntimeService:
    """为单个数据库连接构建真实普通微信支付运行时。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=integration,
        event_repo=OrderEventRepo(handle),
    )


async def _seed_order_and_member(connection: aiosqlite.Connection) -> None:
    """写入待支付订单、会员身份和待保持不变的资产。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '微信预支付后台取消竞态会员', "
        "'high', 1)",
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
                        "product_id": "p_admin_cancel_wechat_prepay_r40",
                        "title": "微信预支付后台取消竞态蛋糕",
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


async def _attempt_admin_cancel(
    service: OrderAdminStatusService,
) -> tuple[str, str]:
    """在生产后台应用服务等价事务中执行真实取消。"""
    try:
        async with service._order_repo.transaction():
            result = await service.update_admin_order_status(ORDER_ID, "cancelled")
            status = str(result["status"])
        return "ok", status
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_prepare_payment(
    service: OrderPaymentRuntimeService,
) -> tuple[str, str]:
    """执行普通微信预支付并转换可断言结果。"""
    try:
        result = await service.prepare_payment(ORDER_ID, user_id=USER_ID)
        return "ok", str(result.payload.get("package", ""))
    except ValueError as exc:
        return "conflict", str(exc)


async def _read_final_state(
    connection: aiosqlite.Connection,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    """读取订单、余额、余额流水和订单事件。"""
    order_rows = await connection.execute_fetchall(
        "SELECT status, payment FROM orders WHERE id = ?",
        (ORDER_ID,),
    )
    balance_rows = await connection.execute_fetchall(
        "SELECT stored_value_fen, points FROM member_balance WHERE mobile = ?",
        (MOBILE,),
    )
    balance_ledger = await connection.execute_fetchall(
        "SELECT unique_id, amount_fen, balance_after_fen "
        "FROM balance_ledger WHERE biz_id = ? ORDER BY id",
        (ORDER_ID,),
    )
    event_rows = await connection.execute_fetchall(
        "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
        (ORDER_ID,),
    )
    return order_rows, balance_rows, balance_ledger, event_rows


def _assert_cancelled_without_local_assets(
    order_rows: list[dict[str, object]],
    balance_rows: list[dict[str, object]],
    balance_ledger: list[dict[str, object]],
    event_rows: list[dict[str, object]],
) -> None:
    """取消后不得留下余额、积分或支付事件副作用。"""
    assert len(order_rows) == 1
    assert str(order_rows[0]["status"]) == OrderStatus.CANCELLED.value
    payment = json.loads(str(order_rows[0]["payment"]))
    assert str(payment["status"]) == "unpaid"
    assert int(payment.get("externalPaidFen", 0)) == ORDER_AMOUNT_FEN
    assert int(payment.get("wechatPrepayFen", 0)) == ORDER_AMOUNT_FEN
    assert int(balance_rows[0]["stored_value_fen"]) == INITIAL_BALANCE_FEN
    assert int(balance_rows[0]["points"]) == INITIAL_POINTS
    assert balance_ledger == []
    assert [(str(row["status"]), str(row["operator"])) for row in event_rows] == [
        (OrderStatus.CANCELLED.value, "admin")
    ]


async def _assert_late_notify_is_refund_fact(
    runtime: OrderPaymentRuntimeService,
    connection: aiosqlite.Connection,
) -> None:
    """取消后迟到到账只能留下一次待退款事实。"""
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
    order_rows, balance_rows, balance_ledger, event_rows = await _read_final_state(
        connection
    )
    assert duplicate_notify == {"duplicate": True}
    assert str(late_notify["status"]) == OrderStatus.CANCELLED.value
    assert str(late_notify["paymentStatus"]) == "paid"
    assert str(late_notify["paymentRefundStatus"]) == "pending"
    assert int(late_notify["paymentRefundAmountFen"]) == ORDER_AMOUNT_FEN
    assert len(order_rows) == 1
    payment = json.loads(str(order_rows[0]["payment"]))
    assert str(payment["status"]) == "paid"
    assert str(payment["method"]) == "wechat"
    assert str(payment["transactionId"]) == TRANSACTION_ID
    assert str(payment["refundStatus"]) == "pending"
    assert int(payment["refundAmountFen"]) == ORDER_AMOUNT_FEN
    assert int(balance_rows[0]["stored_value_fen"]) == INITIAL_BALANCE_FEN
    assert int(balance_rows[0]["points"]) == INITIAL_POINTS
    assert balance_ledger == []
    assert [(str(row["status"]), str(row["operator"])) for row in event_rows] == [
        (OrderStatus.CANCELLED.value, "admin"),
        ("paid", "wechat-pay"),
    ]
    transaction_rows = await connection.execute_fetchall(
        "SELECT transaction_id, order_id FROM payment_transactions WHERE order_id = ?",
        (ORDER_ID,),
    )
    assert [
        (str(row["transaction_id"]), str(row["order_id"])) for row in transaction_rows
    ] == [(TRANSACTION_ID, ORDER_ID)]


@pytest.mark.asyncio
@pytest.mark.parametrize("window", ["after_lock", "during_prepay"])
async def test_admin_cancel_and_wechat_prepay_race_never_returns_cancelled_session(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    window: str,
) -> None:
    """两个预支付窗口都不得返回已取消订单的支付会话。"""
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-r40")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-r40")
    database_path = tmp_path / f"admin-cancel-wechat-prepay-{window}-r40.db"
    admin_connection = await init_db(str(database_path))
    payment_connection = await init_db(str(database_path))
    admin_handle = DatabaseHandle(admin_connection)
    payment_handle = DatabaseHandle(payment_connection)
    try:
        await _seed_order_and_member(admin_connection)
        integration = _BlockingWechatPayIntegration(
            block_prepay=window == "during_prepay"
        )
        runtime = _build_runtime(payment_handle, integration)
        admin_service = _build_admin_service(admin_handle)
        lock_committed = asyncio.Event()

        original_lock = runtime._lock_wechat_prepay_amount

        async def lock_then_wait(order, total_fen: int):
            """在金额已提交但预下单尚未开始时放行后台取消。"""
            locked = await original_lock(order, total_fen)
            lock_committed.set()
            if window == "after_lock":
                await asyncio.wait_for(
                    integration.admin_cancel_committed.wait(),
                    timeout=5,
                )
            return locked

        if window == "after_lock":
            monkeypatch.setattr(
                runtime,
                "_lock_wechat_prepay_amount",
                lock_then_wait,
            )

        payment_task = asyncio.create_task(_attempt_prepare_payment(runtime))
        await asyncio.wait_for(
            lock_committed.wait()
            if window == "after_lock"
            else integration.prepay_started.wait(),
            timeout=5,
        )
        admin_result = await _attempt_admin_cancel(admin_service)
        integration.admin_cancel_committed.set()
        payment_result = await payment_task

        order_rows, balance_rows, balance_ledger, event_rows = await _read_final_state(
            admin_connection
        )
        assert admin_result == ("ok", OrderStatus.CANCELLED.value)
        assert payment_result == ("conflict", "订单已取消")
        assert integration.prepay_amounts == [ORDER_AMOUNT_FEN]
        _assert_cancelled_without_local_assets(
            order_rows,
            balance_rows,
            balance_ledger,
            event_rows,
        )

        await _assert_late_notify_is_refund_fact(runtime, admin_connection)
    finally:
        await close_db(payment_connection)
        await close_db(admin_connection)
