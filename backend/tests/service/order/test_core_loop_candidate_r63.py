"""MiniApp 核心闭环 r63：同一张优惠券被两个订单先后应用快照时的跨单核销复核。"""

import json

import aiosqlite
import pytest

from app.config import settings
from app.database import init_db
from app.models.coupon import CouponTemplate, CouponType
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.models.order import Order, OrderStatus
from app.repository.base import DatabaseHandle
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment, now_text
from tests.service.order.test_core_loop_candidate_r41 import (
    _build_coupon_service,
)

MOBILE = "13800003063"
OPENID = "coupon_cross_order_r63_001"
USER_ID = f"wx_{OPENID}"
ORDER_A = "order_coupon_cross_a_r63_001"
ORDER_B = "order_coupon_cross_b_r63_001"
COUPON_ID = "coupon_cross_order_r63_001"
TEMPLATE_ID = "template_cross_order_r63_001"
ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 1_000
EXTERNAL_FEN = ORDER_AMOUNT_FEN - COUPON_FEN
TRANSACTION_A = "4200000000202609266300000001"
TRANSACTION_B = "4200000000202609266300000002"
EVENT_PAY_A = "EV-coupon-cross-r63-pay-a"
EVENT_PAY_B = "EV-coupon-cross-r63-pay-b"
EVENT_PAY_B_RETRY = "EV-coupon-cross-r63-pay-b-retry"
EVENT_REFUND_A = "EV-coupon-cross-r63-refund-a"
MCH_ID = "mch-coupon-cross-order-r63"
APP_ID = "appid-coupon-cross-order-r63"


class _LocalWechatPay:
    """为支付与退款通知提供不触网的本地集成。"""

    def __init__(self) -> None:
        self.current: dict = {}

    def is_ready(self) -> bool:
        return False

    def verify_notify_signature(
        self,
        raw_body: bytes,
        headers: dict,
        *,
        now_seconds: int | None = None,
    ) -> bool:
        return True

    def decrypt_notify_resource(self, resource: dict) -> dict:
        return dict(self.current)

    def format_success_time(self, value: str) -> str:
        return "2026-09-26 11:00:00"


def _build_payment_service(
    handle: DatabaseHandle,
) -> tuple[OrderPaymentRuntimeService, _LocalWechatPay]:
    """构建真实微信支付与退款通知运行时，并返回可编排的本地通知桩。"""
    wechat = _LocalWechatPay()
    service = OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=wechat,
        event_repo=OrderEventRepo(handle),
    )
    return service, wechat


def _notify_body(event_id: str, event_type: str) -> bytes:
    """构造微信通知外层载荷。"""
    return json.dumps(
        {"id": event_id, "event_type": event_type, "resource": {"kind": "refund"}},
        ensure_ascii=False,
    ).encode("utf-8")


def _pay_transaction(order_id: str, transaction_id: str) -> dict:
    """构造覆盖券后外部支付腿的支付成功通知内容。"""
    return {
        "out_trade_no": order_id,
        "trade_state": "SUCCESS",
        "mchid": MCH_ID,
        "appid": APP_ID,
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": transaction_id,
        "success_time": "2026-09-26T11:00:00+08:00",
    }


def _refund_transaction() -> dict:
    """构造与订单 A 外部支付腿完全匹配的全额退款通知内容。"""
    return {
        "mchid": MCH_ID,
        "out_trade_no": ORDER_A,
        "transaction_id": TRANSACTION_A,
        "out_refund_no": "R-coupon-cross-r63-refund-a",
        "refund_id": "refund-coupon-cross-r63-a",
        "refund_status": "SUCCESS",
        "success_time": "2026-09-26T11:30:00+08:00",
        "amount": {
            "total": EXTERNAL_FEN,
            "refund": EXTERNAL_FEN,
            "payer_total": EXTERNAL_FEN,
            "payer_refund": EXTERNAL_FEN,
        },
    }


async def _notify_payment(
    service: OrderPaymentRuntimeService,
    wechat: _LocalWechatPay,
    order_id: str,
    transaction_id: str,
    event_id: str,
) -> tuple[str, str]:
    """执行真实支付成功通知入口并区分业务结果与锁失败。"""
    import sqlite3

    wechat.current = _pay_transaction(order_id, transaction_id)
    try:
        result = await service.handle_wechat_payment_notify(
            raw_body=_notify_body(event_id, "TRANSACTION.SUCCESS"),
            headers={},
        )
        return "ok", str(result.get("status", ""))
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _notify_refund(
    service: OrderPaymentRuntimeService,
    wechat: _LocalWechatPay,
    event_id: str,
) -> tuple[str, str]:
    """执行真实退款成功通知入口并区分业务结果与锁失败。"""
    import sqlite3

    wechat.current = _refund_transaction()
    try:
        result = await service.handle_wechat_refund_notify(
            raw_body=_notify_body(event_id, "REFUND.SUCCESS"),
            headers={},
        )
        return "ok", str(result.get("kind", ""))
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _seed_two_orders_sharing_one_coupon(
    connection: aiosqlite.Connection,
) -> None:
    """写入会员、同一张券，以及都持有该券快照的两个待支付订单。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '跨单券快照会员', 'high', 1)",
        (f"cm_{ORDER_A}", MOBILE),
    )
    await connection.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (f"cil_{ORDER_A}", f"cm_{ORDER_A}", OPENID, OPENID),
    )
    await connection.execute(
        "INSERT INTO member_balance (mobile, stored_value_fen, points) VALUES (?, ?, 0)",
        (MOBILE, 0),
    )
    for order_id in (ORDER_A, ORDER_B):
        await connection.execute(
            "INSERT INTO sessions (id, channel, user_id, status) "
            "VALUES (?, 'miniapp', ?, 'active')",
            (f"session_{order_id}", USER_ID),
        )
        await OrderRepo(connection).create_order(
            Order(
                id=order_id,
                session_id=f"session_{order_id}",
                channel="miniapp",
                user_id=USER_ID,
                products="[]",
                total_amount=ORDER_AMOUNT_FEN / 100,
                delivery="{}",
                payment=json.dumps(
                    build_initial_payment(now_text()), ensure_ascii=False
                ),
                status=OrderStatus.PENDING,
                remark="",
                created_at=now_text(),
                updated_at=now_text(),
            )
        )
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=TEMPLATE_ID,
            name="跨单券快照测试券",
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
            coupon_group_id=TEMPLATE_ID,
            title="跨单券快照测试券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id=TEMPLATE_ID,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()

    # 关键前置：同一张券在两个订单上各留下一份 partial 快照，券本身仍是 TAKE。
    coupon_service = _build_coupon_service(DatabaseHandle(connection))
    for order_id in (ORDER_A, ORDER_B):
        await coupon_service.apply_coupon(
            order_id,
            user_id=USER_ID,
            coupon_id=COUPON_ID,
        )
    await connection.commit()


async def _read_state(connection: aiosqlite.Connection) -> dict[str, list[dict]]:
    """读取两个订单、券流水、交易认领与通知收件箱的最终事实。"""
    queries = {
        "orders": (
            "SELECT id, status, payment FROM orders WHERE id IN (?, ?) ORDER BY id",
            (ORDER_A, ORDER_B),
        ),
        "coupons": (
            "SELECT status, order_no, cycle_no, deducted_fen FROM coupon_inventory "
            "WHERE coupon_id = ? ORDER BY id",
            (COUPON_ID,),
        ),
        "transactions": (
            "SELECT transaction_id, order_id FROM payment_transactions "
            "WHERE transaction_id IN (?, ?) ORDER BY transaction_id",
            (TRANSACTION_A, TRANSACTION_B),
        ),
    }
    return {
        name: await connection.execute_fetchall(sql, parameters)
        for name, (sql, parameters) in queries.items()
    }


@pytest.mark.asyncio
async def test_coupon_snapshot_on_two_orders_cannot_double_spend(
    tmp_path,
) -> None:
    """两个订单都持券快照时，第二个订单的支付必须被跨单核销守卫拒绝并回滚。"""
    database_path = tmp_path / "coupon-cross-order-r63.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    previous_mch = settings.WECHAT_PAY_MCH_ID
    previous_app = settings.WECHAT_MINIAPP_APP_ID
    try:
        settings.WECHAT_PAY_MCH_ID = MCH_ID
        settings.WECHAT_MINIAPP_APP_ID = APP_ID
        await _seed_two_orders_sharing_one_coupon(connection)
        service, wechat = _build_payment_service(handle)

        pay_a = await _notify_payment(
            service, wechat, ORDER_A, TRANSACTION_A, EVENT_PAY_A
        )
        assert pay_a[0] == "ok"

        pay_b = await _notify_payment(
            service, wechat, ORDER_B, TRANSACTION_B, EVENT_PAY_B
        )
        # 券已随订单 A 退款退回，最新态为 BACK，核销无法落行，必须按失败阻断支付。
        assert pay_b == ("conflict", "优惠券已被其他订单核销")
        # 重投不得因为首次失败而放行，双花必须稳定拒绝。
        pay_b_retry = await _notify_payment(
            service, wechat, ORDER_B, TRANSACTION_B, EVENT_PAY_B_RETRY
        )
        assert pay_b_retry == ("conflict", "优惠券已被其他订单核销")

        state = await _read_state(connection)
        orders = {str(row["id"]): row for row in state["orders"]}
        assert str(orders[ORDER_A]["status"]) == OrderStatus.PENDING.value
        payment_a = json.loads(str(orders[ORDER_A]["payment"]))
        assert payment_a["status"] == "paid"
        assert payment_a["transactionId"] == TRANSACTION_A
        # 关键断言：订单 B 的支付落账与交易认领都随事务回滚，券折扣未白拿。
        assert str(orders[ORDER_B]["status"]) == OrderStatus.PENDING.value
        payment_b = json.loads(str(orders[ORDER_B]["payment"]))
        assert payment_b["status"] == "partial"
        assert str(payment_b.get("transactionId", "")) == ""
        assert [dict(row) for row in state["coupons"]] == [
            {
                "status": CouponStatus.TAKE,
                "order_no": "",
                "cycle_no": 0,
                "deducted_fen": 0,
            },
            {
                "status": CouponStatus.CONSUME,
                "order_no": ORDER_A,
                "cycle_no": 0,
                "deducted_fen": COUPON_FEN,
            },
        ]
        assert [dict(row) for row in state["transactions"]] == [
            {"transaction_id": TRANSACTION_A, "order_id": ORDER_A}
        ]
    finally:
        settings.WECHAT_PAY_MCH_ID = previous_mch
        settings.WECHAT_MINIAPP_APP_ID = previous_app
        await connection.close()


@pytest.mark.asyncio
async def test_refunded_coupon_returns_to_holder_without_writing_back_for_others(
    tmp_path,
) -> None:
    """券随订单 A 全额退款退回后归客户持有，退回腿不替他人写下 BACK 行。

    **本测试在 r78 被重写，其原期望值本身是 `M-20260926-028` 的直接后果。**
    原名 `test_refunded_coupon_cannot_be_reused_by_another_order`，断言订单 B 的
    支付必须被「优惠券核销未落账」阻断——那时的实现里 `BACK` 是事实终态，券永久
    作废，所以 B 用不了是**缺陷的表现**而不是保护。r78 修好后语义变了：订单 A 已
    全额退款（现金退满、券退回），该券的唯一一次合法抵扣机会就是留给 B，B 用得。

    重写时保留本测试真正要保护的不变量，并把它显式写出来：**退回腿写的 `BACK`
    只归属真正核销的订单 A，绝不替别人写**。若把 `BACK` 写成 B 的，或让 B 白拿
    抵扣而没有真实核销行，下面的断言都会红。
    """
    database_path = tmp_path / "coupon-refund-reuse-r63.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    previous_mch = settings.WECHAT_PAY_MCH_ID
    previous_app = settings.WECHAT_MINIAPP_APP_ID
    try:
        settings.WECHAT_PAY_MCH_ID = MCH_ID
        settings.WECHAT_MINIAPP_APP_ID = APP_ID
        await _seed_two_orders_sharing_one_coupon(connection)
        service, wechat = _build_payment_service(handle)

        pay_a = await _notify_payment(
            service, wechat, ORDER_A, TRANSACTION_A, EVENT_PAY_A
        )
        assert pay_a[0] == "ok"
        refund_a = await _notify_refund(service, wechat, EVENT_REFUND_A)
        assert refund_a[0] == "ok"

        pay_b = await _notify_payment(
            service, wechat, ORDER_B, TRANSACTION_B, EVENT_PAY_B
        )
        # 券已随订单 A 全额退款回到客户手里，最新态是新周期 TAKE，B 可合法使用。
        assert pay_b[0] == "ok"

        state = await _read_state(connection)
        orders = {str(row["id"]): row for row in state["orders"]}
        assert str(orders[ORDER_B]["status"]) == OrderStatus.PENDING.value
        payment_b = json.loads(str(orders[ORDER_B]["payment"]))
        assert payment_b["status"] == "paid"
        assert payment_b["transactionId"] == TRANSACTION_B
        # 关键断言：BACK 行只归属真正核销的订单 A；B 在第二周期真实核销，
        # 全表不存在任何 order_no 为 B 的 BACK 行。
        assert [dict(row) for row in state["coupons"]] == [
            {
                "status": CouponStatus.TAKE,
                "order_no": "",
                "cycle_no": 0,
                "deducted_fen": 0,
            },
            {
                "status": CouponStatus.CONSUME,
                "order_no": ORDER_A,
                "cycle_no": 0,
                "deducted_fen": COUPON_FEN,
            },
            {
                "status": CouponStatus.BACK,
                "order_no": ORDER_A,
                "cycle_no": 0,
                "deducted_fen": COUPON_FEN,
            },
            {
                "status": CouponStatus.TAKE,
                "order_no": ORDER_A,
                "cycle_no": 1,
                "deducted_fen": 0,
            },
            {
                "status": CouponStatus.CONSUME,
                "order_no": ORDER_B,
                "cycle_no": 1,
                "deducted_fen": COUPON_FEN,
            },
        ]
        assert [dict(row) for row in state["transactions"]] == [
            {"transaction_id": TRANSACTION_A, "order_id": ORDER_A},
            {"transaction_id": TRANSACTION_B, "order_id": ORDER_B},
        ]
    finally:
        settings.WECHAT_PAY_MCH_ID = previous_mch
        settings.WECHAT_MINIAPP_APP_ID = previous_app
        await connection.close()
