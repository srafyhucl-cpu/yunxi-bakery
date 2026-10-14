"""MiniApp 核心闭环 r61：用户取消、微信支付通知与后台制作三方并发候选复核。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.models.member import CouponStatus
from app.models.order import OrderStatus
from app.repository.base import DatabaseHandle
from app.repository.order_repo import OrderRepo
from app.service.order import notify_intake
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.status_flow import OrderAdminStatusService
from tests.service.order.test_core_loop_candidate_r41 import (
    COUPON_FEN,
    COUPON_ID,
    EXTERNAL_FEN,
    MOBILE,
    ORDER_AMOUNT_FEN,
    ORDER_ID,
    TRANSACTION_ID,
    USER_ID,
    _build_cancellation_service,
)
from tests.service.order.test_core_loop_candidate_r48 import (
    _attempt_cancel,
    _attempt_payment_notify,
    _build_runtime_service,
)
from tests.service.order.test_core_loop_candidate_r58 import _build_admin_service

EVENT_ID = "EV-cancel-payment-admin-making-race-r61-001"
INBOX_KEY = f"wechat_pay_notify:{EVENT_ID}"
MCH_ID = "mch-cancel-payment-admin-making-r61"
APP_ID = "appid-cancel-payment-admin-making-r61"


async def _seed_confirmed_unpaid_order(connection: aiosqlite.Connection) -> None:
    """写入已确认、未支付且已锁定微信预下单金额的合成订单。"""
    await _seed_member_and_coupon(connection)
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id) VALUES (?, 'miniapp', ?)",
        (f"session_{ORDER_ID}", USER_ID),
    )
    await connection.execute(
        "INSERT INTO orders (id, session_id, channel, user_id, products, "
        "total_amount, delivery, payment, status, remark, created_at, updated_at) "
        "VALUES (?, ?, 'miniapp', ?, '[]', ?, '{}', ?, 'pending', '', "
        "'2026-09-25 09:00:00', '2026-09-25 09:00:00')",
        (
            ORDER_ID,
            f"session_{ORDER_ID}",
            USER_ID,
            ORDER_AMOUNT_FEN / 100,
            json.dumps(
                {
                    "status": "unpaid",
                    "method": "",
                    "externalPaidFen": EXTERNAL_FEN,
                    "wechatPrepayFen": EXTERNAL_FEN,
                    "couponId": COUPON_ID,
                    "couponFen": COUPON_FEN,
                    "remainFen": EXTERNAL_FEN,
                    "balanceFen": 0,
                    "pointsFen": 0,
                    "pointsUsed": 0,
                    "createdAt": "2026-09-25 09:00:00",
                },
                ensure_ascii=False,
            ),
        ),
    )
    await connection.commit()
    await connection.execute(
        "UPDATE orders SET status = ? WHERE id = ?",
        (OrderStatus.CONFIRMED.value, ORDER_ID),
    )
    await connection.commit()


async def _seed_member_and_coupon(connection: aiosqlite.Connection) -> None:
    """写入会员身份与可用优惠券，使券核销与清空可观测。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '三方并发会员', 'high', 1)",
        (f"cm_{ORDER_ID}", MOBILE),
    )
    await connection.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (
            f"cil_{ORDER_ID}",
            f"cm_{ORDER_ID}",
            USER_ID.removeprefix("wx_"),
            USER_ID.removeprefix("wx_"),
        ),
    )
    await connection.execute(
        "INSERT INTO member_balance (mobile, stored_value_fen, points) "
        "VALUES (?, 0, 0)",
        (MOBILE,),
    )
    await connection.execute(
        "INSERT INTO coupon_inventory (coupon_id, status, mobile, coupon_group_id, "
        "title, value_fen, source, occurred_at, template_id, valid_from, valid_until) "
        "VALUES (?, ?, ?, 'template_r61', '三方并发测试券', ?, 'import', "
        "'2026-08-01 09:00:00', 'template_r61', '2026-08-01', '2026-12-31')",
        (COUPON_ID, CouponStatus.TAKE, MOBILE, COUPON_FEN),
    )
    await connection.commit()


def _payment_transaction() -> dict:
    """构造与券后应付金额一致的微信支付成功通知。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": MCH_ID,
        "appid": APP_ID,
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T12:00:00+08:00",
    }


def _notify_body() -> bytes:
    """构造本地微信支付通知入口载荷。"""
    return json.dumps(
        {
            "id": EVENT_ID,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {},
        },
        ensure_ascii=False,
    ).encode("utf-8")


async def _attempt_admin_making(
    service: OrderAdminStatusService,
) -> tuple[str, str]:
    """在独立后台请求事务中执行真实制作状态更新。"""
    try:
        async with service._order_repo.transaction():
            result = await service.update_admin_order_status(ORDER_ID, "making")
        return "ok", str(result["status"])
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _read_state(connection: aiosqlite.Connection) -> dict[str, list[dict]]:
    """读取订单、交易、事件、券、积分和 inbox 最终事实。"""
    queries = {
        "order": (
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        ),
        "transactions": (
            "SELECT transaction_id, order_id FROM payment_transactions "
            "WHERE transaction_id = ?",
            (TRANSACTION_ID,),
        ),
        "events": (
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "coupons": (
            "SELECT coupon_id, status, order_no, deducted_fen FROM coupon_inventory "
            "WHERE coupon_id = ? ORDER BY id",
            (COUPON_ID,),
        ),
        "points_ledger": (
            "SELECT unique_id, event_type FROM points_ledger WHERE biz_id = ? "
            "ORDER BY id",
            (ORDER_ID,),
        ),
        "balance_ledger": (
            "SELECT unique_id, amount_fen FROM balance_ledger WHERE biz_id = ? "
            "ORDER BY id",
            (ORDER_ID,),
        ),
        "inbox": (
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key = ?",
            (INBOX_KEY,),
        ),
    }
    return {
        name: await connection.execute_fetchall(sql, parameters)
        for name, (sql, parameters) in queries.items()
    }


def _assert_state(
    state: dict[str, list[dict]],
    *,
    first_winner: str,
    payment_attempts: int,
) -> None:
    """断言三方并发后只形成一套终态，且取消单永不进入制作。"""
    assert len(state["order"]) == 1
    order = state["order"][0]
    payment = json.loads(str(order["payment"]))
    assert payment["status"] == "paid"
    assert payment["method"] == "wechat"
    assert payment["transactionId"] == TRANSACTION_ID
    assert [dict(row) for row in state["transactions"]] == [
        {"transaction_id": TRANSACTION_ID, "order_id": ORDER_ID}
    ]
    assert [dict(row) for row in state["balance_ledger"]] == []
    if first_winner == "cancel":
        assert str(order["status"]) == OrderStatus.CANCELLED.value
        assert payment["refundStatus"] == "pending"
        assert int(payment.get("refundAmountFen", 0)) == EXTERNAL_FEN
        assert str(payment.get("couponId", "")) == ""
        assert int(payment.get("couponFen", 0)) == 0
        assert int(payment.get("pointsAwarded", 0) or 0) == 0
        assert [dict(row) for row in state["events"]] == [
            {
                "status": OrderStatus.CANCELLED.value,
                "operator": f"miniapp:{USER_ID}",
            },
            {"status": "paid", "operator": "wechat-pay"},
        ]
        assert [dict(row) for row in state["coupons"]] == [
            {
                "coupon_id": COUPON_ID,
                "status": CouponStatus.TAKE,
                "order_no": "",
                "deducted_fen": 0,
            }
        ]
        assert state["points_ledger"] == []
    else:
        assert str(order["status"]) == "making"
        assert str(payment.get("refundStatus", "")) == ""
        assert payment["couponId"] == COUPON_ID
        assert int(payment["couponFen"]) == COUPON_FEN
        assert [dict(row) for row in state["events"]] == [
            {"status": "paid", "operator": "wechat-pay"},
            {"status": "making", "operator": "admin"},
        ]
        assert [dict(row) for row in state["coupons"]] == [
            {
                "coupon_id": COUPON_ID,
                "status": CouponStatus.TAKE,
                "order_no": "",
                "deducted_fen": 0,
            },
            {
                "coupon_id": COUPON_ID,
                "status": CouponStatus.CONSUME,
                "order_no": ORDER_ID,
                "deducted_fen": COUPON_FEN,
            },
        ]
        assert [dict(row) for row in state["points_ledger"]] == [
            {"unique_id": f"points:award:{ORDER_ID}", "event_type": "order_award"}
        ]
    assert [dict(row) for row in state["inbox"]] == [
        {
            "message_key": INBOX_KEY,
            "status": "processed",
            "attempt_count": payment_attempts,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["cancel", "payment"])
async def test_cancel_payment_and_admin_making_race_has_single_legal_terminal(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    first_winner: str,
) -> None:
    """取消先到时已取消单不得进入制作，支付先到时制作只能落一次。"""
    database_path = tmp_path / f"cancel-payment-admin-making-{first_winner}-r61.db"
    cancel_connection = await init_db(str(database_path))
    payment_connection = await init_db(str(database_path))
    admin_connection = await init_db(str(database_path))
    cancel_handle = DatabaseHandle(cancel_connection)
    payment_handle = DatabaseHandle(payment_connection)
    admin_handle = DatabaseHandle(admin_connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        await _seed_confirmed_unpaid_order(cancel_connection)
        cancel_service = _build_cancellation_service(cancel_handle)
        payment_service = _build_runtime_service(payment_handle)
        admin_service = _build_admin_service(admin_handle)
        raw_body = _notify_body()

        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_verify_wechat_notify_signature",
            lambda self, payload, headers: True,
        )
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_decrypt_wechat_resource",
            lambda self, resource: _payment_transaction(),
        )

        initial_reads = asyncio.Barrier(3)
        winner_committed = asyncio.Event()
        payment_claim_committed = asyncio.Event()
        observed_handles: set[int] = set()
        cancel_handle_key = id(cancel_handle)
        payment_handle_key = id(payment_handle)
        admin_handle_key = id(admin_handle)
        original_get_order = OrderRepo.get_order
        original_claim_notify = notify_intake.claim_notify

        async def read_initial_snapshot_together(repo: OrderRepo, order_id: str):
            """让三方先读同一 confirmed+unpaid 快照，再按指定胜者提交。"""
            handle_key = id(repo._db)
            if order_id != ORDER_ID or handle_key not in {
                cancel_handle_key,
                payment_handle_key,
                admin_handle_key,
            }:
                return await original_get_order(repo, order_id)
            # 认领提交必须早于任何业务读，否则延迟事务升级写锁会读到过期快照
            await asyncio.wait_for(payment_claim_committed.wait(), timeout=5)
            order = await original_get_order(repo, order_id)
            if handle_key in observed_handles:
                return order
            observed_handles.add(handle_key)
            await asyncio.wait_for(initial_reads.wait(), timeout=5)
            role = {
                cancel_handle_key: "cancel",
                payment_handle_key: "payment",
                admin_handle_key: "admin",
            }[handle_key]
            if role != first_winner:
                await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        async def commit_payment_claim_before_business(
            db,
            event_id: str,
            payload: dict | None = None,
            *,
            lease_seconds: int = notify_intake.DEFAULT_NOTIFY_LEASE_SECONDS,
        ) -> dict:
            """先提交通知认领，避免 claim 写锁改变业务首胜顺序。"""
            claim = await original_claim_notify(
                db,
                event_id,
                payload,
                lease_seconds=lease_seconds,
            )
            if id(db) == payment_handle_key:
                await db.commit()
                payment_claim_committed.set()
            return claim

        monkeypatch.setattr(OrderRepo, "get_order", read_initial_snapshot_together)
        monkeypatch.setattr(
            notify_intake,
            "claim_notify",
            commit_payment_claim_before_business,
        )

        async def run_cancel() -> tuple[str, str]:
            result = await _attempt_cancel(cancel_service)
            if first_winner == "cancel":
                winner_committed.set()
            return result

        async def run_payment() -> tuple[str, dict | str]:
            result = await _attempt_payment_notify(payment_service, raw_body)
            if first_winner == "payment":
                winner_committed.set()
            return result

        async def run_admin() -> tuple[str, str]:
            result = await _attempt_admin_making(admin_service)
            if first_winner == "admin":
                winner_committed.set()
            return result

        payment_task = asyncio.create_task(run_payment())
        await asyncio.wait_for(payment_claim_committed.wait(), timeout=5)
        cancel_result, payment_result, admin_result = await asyncio.gather(
            run_cancel(),
            payment_task,
            run_admin(),
        )
        assert observed_handles == {
            cancel_handle_key,
            payment_handle_key,
            admin_handle_key,
        }
        # 后台旧快照为未支付，必须被支付完成守卫拒绝。
        assert admin_result[0] == "conflict"
        assert admin_result[1] == "订单未完成支付，不能进入履约"

        if first_winner == "cancel":
            assert cancel_result == ("ok", OrderStatus.CANCELLED.value)
        else:
            assert cancel_result[0] in {"conflict", "locked"}

        # 取消先到时支付通知会被取消事务写锁挡住，需按 inbox 重试后补记迟到到账。
        payment_attempts = 1
        if payment_result[0] != "ok":
            assert payment_result[0] == "locked"
            assert first_winner == "cancel"
            await payment_connection.execute(
                "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
                "WHERE message_key = ?",
                (INBOX_KEY,),
            )
            await payment_connection.commit()
            payment_result = await _attempt_payment_notify(payment_service, raw_body)
            payment_attempts = 2
            assert payment_result[0] == "ok"

        admin_retry = await _attempt_admin_making(admin_service)
        if first_winner == "cancel":
            assert admin_retry[0] == "conflict"
            assert admin_retry[1] == "当前订单状态不允许切换到目标状态"
        else:
            assert admin_retry == ("ok", "making")

        duplicate_result = await _attempt_payment_notify(payment_service, raw_body)
        await cancel_handle.commit()
        await payment_handle.commit()
        await admin_handle.commit()
        assert duplicate_result == ("ok", {"duplicate": True})

        state = await _read_state(cancel_connection)
        _assert_state(
            state,
            first_winner=first_winner,
            payment_attempts=payment_attempts,
        )
    finally:
        await close_db(admin_connection)
        await close_db(payment_connection)
        await close_db(cancel_connection)
