"""MiniApp 核心闭环 r47：用户取消与支付/退款查询恢复并发候选复核。"""

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
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.order import notify_intake
from app.service.order.cancellation import OrderCancellationService
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from tests.service.order.test_core_loop_candidate_r41 import (
    BALANCE_FEN,
    COUPON_FEN,
    COUPON_ID,
    EXTERNAL_FEN,
    INITIAL_BALANCE_FEN,
    MOBILE,
    ORDER_ID,
    OUT_REFUND_NO,
    TRANSACTION_ID,
    USER_ID,
    _build_cancellation_service,
    _seed_combined_order,
)

PAYMENT_KEY = f"wechat_pay_notify:query:pay:{ORDER_ID}:{TRANSACTION_ID}"
REFUND_KEY = f"wechat_pay_notify:query:refund:{OUT_REFUND_NO}"
EXPECTED_AWARD_POINTS = EXTERNAL_FEN // 100


class _QueryRecoveryWechat:
    """只为支付与退款查询恢复提供不触网的时间格式化。"""

    def is_ready(self) -> bool:
        return False

    def format_success_time(self, value: str) -> str:
        return "2026-09-25 12:00:00"


def _build_runtime_service(handle: DatabaseHandle) -> OrderPaymentRuntimeService:
    """构建真实支付或退款查询恢复入口。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=_QueryRecoveryWechat(),
        event_repo=OrderEventRepo(handle),
    )


def _payment_transaction() -> dict:
    """构造与组合支付外部腿匹配的支付成功查询结果。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": "mch-cancel-query-race-r47",
        "appid": "appid-cancel-query-race-r47",
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T12:00:00+08:00",
    }


def _refund_query() -> dict:
    """构造与组合支付外部腿匹配的全额退款查询结果。"""
    return {
        "mchid": "mch-cancel-query-race-r47",
        "out_trade_no": ORDER_ID,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": OUT_REFUND_NO,
        "refund_id": "refund-cancel-query-race-r47-001",
        "refund_status": "SUCCESS",
        "success_time": "2026-09-25T12:05:00+08:00",
        "amount": {
            "total": EXTERNAL_FEN,
            "refund": EXTERNAL_FEN,
        },
    }


async def _attempt_cancel(
    service: OrderCancellationService,
) -> tuple[str, str]:
    """在生产等价事务中执行用户取消。"""
    try:
        async with service._order_repo.transaction():
            result = await service.cancel_user_order(ORDER_ID, user_id=USER_ID)
        return "ok", str(result["status"])
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_payment_query(
    service: OrderPaymentRuntimeService,
) -> tuple[str, dict | str]:
    """执行支付查询恢复并区分业务冲突与瞬时锁冲突。"""
    try:
        result = await service.reconcile_pay_from_query(_payment_transaction())
        return "ok", result
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_refund_query(
    service: OrderPaymentRuntimeService,
) -> tuple[str, dict | str]:
    """执行退款查询恢复并区分业务冲突与瞬时锁冲突。"""
    try:
        result = await service.reconcile_refund_from_query(
            _refund_query(),
            payer_total_fen=EXTERNAL_FEN,
        )
        return "ok", result
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _read_final_state(
    connection: aiosqlite.Connection,
) -> dict[str, list[dict]]:
    """读取订单、交易、退款、资产和取消事实。"""
    queries = {
        "orders": (
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        ),
        "transactions": (
            "SELECT order_id FROM payment_transactions "
            "WHERE transaction_id = ? ORDER BY order_id",
            (TRANSACTION_ID,),
        ),
        "refunds": (
            "SELECT out_refund_no, transaction_id, payer_refund_fen, source "
            "FROM wechat_refund_events WHERE order_id = ? ORDER BY out_refund_no",
            (ORDER_ID,),
        ),
        "events": (
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "members": (
            "SELECT stored_value_fen, points FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        ),
        "balance_ledger": (
            "SELECT unique_id, amount_fen, balance_after_fen FROM balance_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "points_ledger": (
            "SELECT unique_id, event_type, amount, total FROM points_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "ledger_operations": (
            "SELECT unique_id, operation_type FROM ledger_operation "
            "WHERE subject_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "refund_operations": (
            "SELECT operation_key, status FROM refund_operation "
            "WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "reconciles": (
            "SELECT unique_id FROM points_refund_reconcile WHERE order_id = ?",
            (ORDER_ID,),
        ),
        "coupons": (
            "SELECT coupon_id, status, order_no, deducted_fen "
            "FROM coupon_inventory WHERE coupon_id = ? ORDER BY id",
            (COUPON_ID,),
        ),
    }
    return {
        name: await connection.execute_fetchall(sql, parameters)
        for name, (sql, parameters) in queries.items()
    }


def _assert_balance_repaid(state: dict[str, list[dict]]) -> None:
    """断言取消或退款恢复只退回一次余额腿。"""
    assert [dict(row) for row in state["members"]] == [
        {"stored_value_fen": INITIAL_BALANCE_FEN, "points": 0}
    ]
    assert [dict(row) for row in state["balance_ledger"]] == [
        {
            "unique_id": f"combined_pay:{ORDER_ID}",
            "amount_fen": -BALANCE_FEN,
            "balance_after_fen": INITIAL_BALANCE_FEN - BALANCE_FEN,
        },
        {
            "unique_id": f"order_refund:{ORDER_ID}",
            "amount_fen": BALANCE_FEN,
            "balance_after_fen": INITIAL_BALANCE_FEN,
        },
    ]


def _assert_payment_recovery(
    state: dict[str, list[dict]],
    cancel_won: bool,
) -> None:
    """断言支付查询在取消前后只形成一套正确支付与资产事实。"""
    payment = json.loads(str(state["orders"][0]["payment"]))
    assert str(state["orders"][0]["status"]) == (
        OrderStatus.CANCELLED.value if cancel_won else OrderStatus.PENDING.value
    )
    assert payment["status"] == "paid"
    assert payment["method"] == "combined"
    assert payment["transactionId"] == TRANSACTION_ID
    assert int(payment["balanceFen"]) == BALANCE_FEN
    assert int(payment["externalPaidFen"]) == EXTERNAL_FEN
    assert [dict(row) for row in state["transactions"]] == [{"order_id": ORDER_ID}]
    assert state["refunds"] == []
    if cancel_won:
        assert [dict(row) for row in state["events"]] == [
            {
                "status": OrderStatus.CANCELLED.value,
                "operator": f"miniapp:{USER_ID}",
            },
            {
                "status": "paid",
                "operator": "wechat-pay",
            },
        ]
        assert int(payment["couponFen"]) == 0
        assert str(payment["refundStatus"]) == "pending"
        assert int(payment.get("pointsAwarded", 0)) == 0
        _assert_balance_repaid(state)
        assert [dict(row) for row in state["points_ledger"]] == []
        assert state["ledger_operations"] == []
        assert [dict(row) for row in state["coupons"]] == [
            {
                "coupon_id": COUPON_ID,
                "status": CouponStatus.TAKE,
                "order_no": "",
                "deducted_fen": 0,
            }
        ]
    else:
        assert [dict(row) for row in state["events"]] == [
            {
                "status": "paid",
                "operator": "wechat-pay",
            }
        ]
        assert int(payment["couponFen"]) == COUPON_FEN
        assert "refundStatus" not in payment
        assert int(payment["pointsAwarded"]) == EXPECTED_AWARD_POINTS
        assert [dict(row) for row in state["members"]] == [
            {
                "stored_value_fen": INITIAL_BALANCE_FEN - BALANCE_FEN,
                "points": EXPECTED_AWARD_POINTS,
            }
        ]
        assert [dict(row) for row in state["balance_ledger"]] == [
            {
                "unique_id": f"combined_pay:{ORDER_ID}",
                "amount_fen": -BALANCE_FEN,
                "balance_after_fen": INITIAL_BALANCE_FEN - BALANCE_FEN,
            }
        ]
        assert [dict(row) for row in state["points_ledger"]] == [
            {
                "unique_id": f"points:award:{ORDER_ID}",
                "event_type": "order_award",
                "amount": EXPECTED_AWARD_POINTS,
                "total": EXPECTED_AWARD_POINTS,
            }
        ]
        assert [dict(row) for row in state["ledger_operations"]] == [
            {
                "unique_id": f"ledger:settle_award:{ORDER_ID}",
                "operation_type": "settle_award",
            }
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
    assert state["refund_operations"] == []
    assert state["reconciles"] == []


def _assert_refund_recovery(
    state: dict[str, list[dict]],
    cancel_won: bool,
    cancel_retry_won: bool,
) -> None:
    """断言退款查询在取消前后只形成一条退款事实且不结算支付资产。"""
    payment = json.loads(str(state["orders"][0]["payment"]))
    assert str(state["orders"][0]["status"]) == (
        OrderStatus.CANCELLED.value
        if cancel_won or cancel_retry_won
        else OrderStatus.PENDING.value
    )
    assert payment["status"] == "partial"
    assert payment["method"] == "combined"
    assert int(payment["couponFen"]) == 0
    assert int(payment["balanceFen"]) == BALANCE_FEN
    assert int(payment["externalPaidFen"]) == EXTERNAL_FEN
    assert payment["refundStatus"] == "full"
    assert int(payment["refundFen"]) == EXTERNAL_FEN
    assert "transactionId" not in payment
    assert [dict(row) for row in state["transactions"]] == [{"order_id": ORDER_ID}]
    assert [dict(row) for row in state["refunds"]] == [
        {
            "out_refund_no": OUT_REFUND_NO,
            "transaction_id": TRANSACTION_ID,
            "payer_refund_fen": EXTERNAL_FEN,
            "source": "query",
        }
    ]
    if cancel_won or cancel_retry_won:
        assert [dict(row) for row in state["events"]] == [
            {
                "status": OrderStatus.CANCELLED.value,
                "operator": f"miniapp:{USER_ID}",
            }
        ]
    else:
        assert state["events"] == []
    _assert_balance_repaid(state)
    assert state["points_ledger"] == []
    assert state["ledger_operations"] == []
    assert state["refund_operations"] == []
    assert state["reconciles"] == []
    assert [dict(row) for row in state["coupons"]] == [
        {
            "coupon_id": COUPON_ID,
            "status": CouponStatus.TAKE,
            "order_no": "",
            "deducted_fen": 0,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("recovery_kind", ["payment", "refund"])
@pytest.mark.parametrize("first_winner", ["cancel", "recovery"])
async def test_cancel_and_query_recovery_race_preserves_assets(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    recovery_kind: str,
    first_winner: str,
) -> None:
    """用户取消与支付/退款查询恢复并发时只能形成一套正确事实。"""
    database_path = tmp_path / (
        f"cancel-{recovery_kind}-query-race-{first_winner}-r47.db"
    )
    cancel_connection = await init_db(str(database_path))
    recovery_connection = await init_db(str(database_path))
    cancel_handle = DatabaseHandle(cancel_connection)
    recovery_handle = DatabaseHandle(recovery_connection)
    try:
        await _seed_combined_order(cancel_connection)
        cancel_service = _build_cancellation_service(cancel_handle)
        recovery_service = _build_runtime_service(recovery_handle)
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-cancel-query-race-r47")
        monkeypatch.setattr(
            settings,
            "WECHAT_MINIAPP_APP_ID",
            "appid-cancel-query-race-r47",
        )

        initial_read_barrier = asyncio.Barrier(2)
        recovery_claim_committed = asyncio.Event()
        winner_committed = asyncio.Event()
        observed_handles: set[int] = set()
        cancel_handle_key = id(cancel_handle)
        recovery_handle_key = id(recovery_handle)
        original_claim_notify_key = notify_intake.claim_notify_key
        original_get_order = OrderRepo.get_order

        async def commit_recovery_claim_before_business(
            db,
            message_key: str,
            payload: dict | None = None,
            *,
            lease_seconds: int = notify_intake.DEFAULT_NOTIFY_LEASE_SECONDS,
        ) -> dict:
            """先提交查询认领，避免取消事务的旧快照被无关 inbox 提交失效。"""
            claim = await original_claim_notify_key(
                db,
                message_key,
                payload,
                lease_seconds=lease_seconds,
            )
            if id(db) == recovery_handle_key:
                await db.commit()
                recovery_claim_committed.set()
            return claim

        async def read_old_snapshot_together(
            repo: OrderRepo,
            order_id: str,
        ):
            """让取消和恢复事务先读同一 partial 快照，再固定提交顺序。"""
            handle_key = id(repo._db)
            if (
                order_id == ORDER_ID
                and handle_key == cancel_handle_key
                and handle_key not in observed_handles
            ):
                await asyncio.wait_for(recovery_claim_committed.wait(), timeout=5)
            order = await original_get_order(repo, order_id)
            if (
                order_id == ORDER_ID
                and handle_key in {cancel_handle_key, recovery_handle_key}
                and handle_key not in observed_handles
            ):
                observed_handles.add(handle_key)
                await asyncio.wait_for(initial_read_barrier.wait(), timeout=5)
                role = "cancel" if handle_key == cancel_handle_key else "recovery"
                if role != first_winner:
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(OrderRepo, "get_order", read_old_snapshot_together)
        monkeypatch.setattr(
            notify_intake,
            "claim_notify_key",
            commit_recovery_claim_before_business,
        )

        async def run_cancel() -> tuple[str, str]:
            result = await _attempt_cancel(cancel_service)
            if first_winner == "cancel":
                winner_committed.set()
            return result

        async def run_recovery() -> tuple[str, dict | str]:
            if recovery_kind == "payment":
                result = await _attempt_payment_query(recovery_service)
            else:
                result = await _attempt_refund_query(recovery_service)
            if first_winner == "recovery":
                winner_committed.set()
            return result

        cancel_result, recovery_result = await asyncio.gather(
            run_cancel(),
            run_recovery(),
        )
        assert observed_handles == {cancel_handle_key, recovery_handle_key}
        if first_winner == "cancel":
            assert cancel_result == ("ok", OrderStatus.CANCELLED.value)
            assert recovery_result[0] == "locked"
        else:
            assert recovery_result[0] == "ok"
            assert cancel_result[0] == "locked"

        if first_winner == "cancel":
            inbox_key = PAYMENT_KEY if recovery_kind == "payment" else REFUND_KEY
            await recovery_connection.execute(
                "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
                "WHERE message_key = ?",
                (inbox_key,),
            )
            await recovery_connection.commit()
            if recovery_kind == "payment":
                retry_result = await _attempt_payment_query(recovery_service)
            else:
                retry_result = await _attempt_refund_query(recovery_service)
            assert retry_result[0] == "ok"
        else:
            cancel_retry_result = await _attempt_cancel(cancel_service)
            cancel_retry_won = cancel_retry_result[0] == "ok"
            if recovery_kind == "payment":
                assert cancel_retry_result == (
                    "conflict",
                    "已支付订单不允许取消",
                )
            else:
                assert cancel_retry_result == (
                    "ok",
                    OrderStatus.CANCELLED.value,
                )
        if first_winner == "cancel":
            cancel_retry_won = False

        inbox_key = PAYMENT_KEY if recovery_kind == "payment" else REFUND_KEY
        duplicate_result = (
            await _attempt_payment_query(recovery_service)
            if recovery_kind == "payment"
            else await _attempt_refund_query(recovery_service)
        )
        await recovery_handle.commit()
        if recovery_kind == "payment":
            assert duplicate_result[0] == "ok"
            assert duplicate_result[1].get("paymentStatus") == "paid"
        else:
            assert duplicate_result == (
                "ok",
                {"duplicate": True, "kind": "duplicate"},
            )

        inbox_rows = await recovery_connection.execute_fetchall(
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key = ?",
            (inbox_key,),
        )
        assert [dict(row) for row in inbox_rows] == [
            {
                "message_key": inbox_key,
                "status": "processed",
                "attempt_count": 2 if first_winner == "cancel" else 1,
            }
        ]
        state = await _read_final_state(cancel_connection)
        if recovery_kind == "payment":
            _assert_payment_recovery(state, first_winner == "cancel")
        else:
            _assert_refund_recovery(
                state,
                first_winner == "cancel",
                cancel_retry_won,
            )
    finally:
        await close_db(recovery_connection)
        await close_db(cancel_connection)
