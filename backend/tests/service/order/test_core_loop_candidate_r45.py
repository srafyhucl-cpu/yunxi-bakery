"""MiniApp 核心闭环 r45：支付查询恢复与退款查询恢复并发候选复核。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.repository.base import DatabaseHandle
from app.repository.order_repo import OrderRepo
from app.service.order import notify_intake
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from tests.service.order.test_core_loop_candidate_r44 import (
    BALANCE_FEN,
    COUPON_FEN,
    COUPON_ID,
    EXTERNAL_FEN,
    INITIAL_BALANCE_FEN,
    MOBILE,
    ORDER_ID,
    OUT_REFUND_NO,
    TRANSACTION_ID,
    _assert_payment_first_assets,
    _assert_refund_first_assets,
    _build_runtime_service,
    _payment_transaction,
    _prepare_combined_partial,
    _seed_order_member_and_coupon,
)

PAYMENT_KEY = f"wechat_pay_notify:query:pay:{ORDER_ID}:{TRANSACTION_ID}"
REFUND_KEY = f"wechat_pay_notify:query:refund:{OUT_REFUND_NO}"


def _refund_query() -> dict:
    """构造主动退款查询恢复使用的全额退款成功结果。"""
    return {
        "mchid": "mch-pay-query-refund-race-r45",
        "out_trade_no": ORDER_ID,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": OUT_REFUND_NO,
        "refund_id": "refund-pay-query-refund-query-race-r45-001",
        "refund_status": "SUCCESS",
        "success_time": "2026-09-25T12:05:00+08:00",
        "amount": {
            "total": EXTERNAL_FEN,
            "refund": EXTERNAL_FEN,
        },
    }


async def _attempt_payment_query(
    service: OrderPaymentRuntimeService,
) -> tuple[str, dict | str]:
    """执行支付查询恢复并区分业务冲突与瞬时锁冲突。"""
    try:
        query = _payment_transaction()
        query["mchid"] = "mch-pay-query-refund-race-r45"
        result = await service.reconcile_pay_from_query(query)
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
    """读取订单、交易、退款、资产、异常和 inbox 最终事实。"""
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
            "SELECT out_refund_no, order_id, transaction_id, payer_refund_fen, "
            "source FROM wechat_refund_events WHERE order_id = ? "
            "ORDER BY out_refund_no",
            (ORDER_ID,),
        ),
        "events": (
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "inbox": (
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key IN (?, ?) ORDER BY message_key",
            (PAYMENT_KEY, REFUND_KEY),
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
            "SELECT operation_key, status, clawback_amount FROM refund_operation "
            "WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "reconciles": (
            "SELECT unique_id FROM points_refund_reconcile WHERE order_id = ? "
            "ORDER BY id",
            (ORDER_ID,),
        ),
        "shortfalls": (
            "SELECT operation_key FROM refund_shortfall_debt WHERE order_id = ? "
            "ORDER BY id",
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


def _assert_common_final_state(
    state: dict[str, list[dict]],
    first_winner: str,
) -> None:
    """断言两个查询入口共同的支付、退款和资产补偿事实。"""
    assert len(state["orders"]) == 1
    assert str(state["orders"][0]["status"]) == "pending"
    payment = json.loads(str(state["orders"][0]["payment"]))
    assert payment["status"] == "paid"
    assert payment["method"] == "combined"
    assert payment["transactionId"] == TRANSACTION_ID
    assert int(payment["couponFen"]) == COUPON_FEN
    assert int(payment["balanceFen"]) == BALANCE_FEN
    assert int(payment["externalPaidFen"]) == EXTERNAL_FEN
    assert int(payment.get("pointsAwarded", 0)) == 0
    assert payment["refundStatus"] == "full"
    assert int(payment["refundFen"]) == EXTERNAL_FEN
    assert [dict(row) for row in state["transactions"]] == [{"order_id": ORDER_ID}]
    assert [dict(row) for row in state["refunds"]] == [
        {
            "out_refund_no": OUT_REFUND_NO,
            "order_id": ORDER_ID,
            "transaction_id": TRANSACTION_ID,
            "payer_refund_fen": EXTERNAL_FEN,
            "source": "query",
        }
    ]
    assert [dict(row) for row in state["events"]] == [
        {"status": "paid", "operator": "wechat-pay"}
    ]
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
    assert state["reconciles"] == []
    assert state["shortfalls"] == []
    assert {
        str(row["message_key"]): (str(row["status"]), int(row["attempt_count"]))
        for row in state["inbox"]
    } == {
        PAYMENT_KEY: ("processed", 1 if first_winner == "payment" else 2),
        REFUND_KEY: ("processed", 1 if first_winner == "refund" else 2),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["payment", "refund"])
async def test_payment_and_refund_query_race_preserves_single_settlement(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    first_winner: str,
) -> None:
    """两个查询入口并发后只能形成一次支付、退款和资产补偿事实。"""
    database_path = tmp_path / f"pay-refund-query-race-{first_winner}-r45.db"
    payment_connection = await init_db(str(database_path))
    refund_connection = await init_db(str(database_path))
    payment_handle = DatabaseHandle(payment_connection)
    refund_handle = DatabaseHandle(refund_connection)
    try:
        await _seed_order_member_and_coupon(payment_connection)
        await _prepare_combined_partial(payment_connection)
        payment_service = _build_runtime_service(payment_handle)
        refund_service = _build_runtime_service(refund_handle)
        monkeypatch.setattr(
            settings, "WECHAT_PAY_MCH_ID", "mch-pay-query-refund-race-r45"
        )
        monkeypatch.setattr(
            settings,
            "WECHAT_MINIAPP_APP_ID",
            "appid-pay-query-refund-race-r44",
        )

        all_claims_committed = asyncio.Event()
        both_snapshots_read = asyncio.Barrier(2)
        winner_committed = asyncio.Event()
        observed_handles: set[int] = set()
        payment_handle_key = id(payment_handle)
        refund_handle_key = id(refund_handle)
        claim_committed = {
            payment_handle_key: asyncio.Event(),
            refund_handle_key: asyncio.Event(),
        }
        original_claim_notify_key = notify_intake.claim_notify_key
        original_get_order = OrderRepo.get_order

        async def commit_claims_before_business(
            db,
            message_key: str,
            payload: dict | None = None,
            *,
            lease_seconds: int = notify_intake.DEFAULT_NOTIFY_LEASE_SECONDS,
        ) -> dict:
            """先提交两个查询 inbox 认领，再同时进入业务事务。"""
            claim = await original_claim_notify_key(
                db,
                message_key,
                payload,
                lease_seconds=lease_seconds,
            )
            handle_key = id(db)
            if handle_key in {payment_handle_key, refund_handle_key}:
                await db.commit()
                claim_committed[handle_key].set()
                if all(event.is_set() for event in claim_committed.values()):
                    all_claims_committed.set()
                await asyncio.wait_for(all_claims_committed.wait(), timeout=5)
            return claim

        async def read_old_snapshot_together(
            repo: OrderRepo,
            order_id: str,
        ):
            """让两个查询事务先读同一 partial 快照，再只允许指定入口提交。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if (
                order_id == ORDER_ID
                and handle_key in {payment_handle_key, refund_handle_key}
                and handle_key not in observed_handles
            ):
                observed_handles.add(handle_key)
                await asyncio.wait_for(both_snapshots_read.wait(), timeout=5)
                role = "payment" if handle_key == payment_handle_key else "refund"
                if role != first_winner:
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(
            notify_intake, "claim_notify_key", commit_claims_before_business
        )
        monkeypatch.setattr(OrderRepo, "get_order", read_old_snapshot_together)

        async def run_payment() -> tuple[str, dict | str]:
            result = await _attempt_payment_query(payment_service)
            if first_winner == "payment":
                winner_committed.set()
            return result

        async def run_refund() -> tuple[str, dict | str]:
            result = await _attempt_refund_query(refund_service)
            if first_winner == "refund":
                winner_committed.set()
            return result

        payment_result, refund_result = await asyncio.gather(
            run_payment(),
            run_refund(),
        )

        initial_inbox_rows = await refund_connection.execute_fetchall(
            "SELECT message_key, status, attempt_count, last_error "
            "FROM inbox_events WHERE message_key IN (?, ?) ORDER BY message_key",
            (PAYMENT_KEY, REFUND_KEY),
        )
        initial_inbox = {str(row["message_key"]): row for row in initial_inbox_rows}
        winner_key = PAYMENT_KEY if first_winner == "payment" else REFUND_KEY
        loser_key = REFUND_KEY if first_winner == "payment" else PAYMENT_KEY
        winner_result = payment_result if first_winner == "payment" else refund_result
        loser_result = refund_result if first_winner == "payment" else payment_result
        assert observed_handles == {payment_handle_key, refund_handle_key}
        assert winner_result[0] == "ok"
        assert loser_result[0] == "locked"
        assert str(initial_inbox[winner_key]["status"]) == "processed"
        assert int(initial_inbox[winner_key]["attempt_count"]) == 1
        assert str(initial_inbox[loser_key]["status"]) == "failed"
        assert int(initial_inbox[loser_key]["attempt_count"]) == 1
        assert "locked" in str(initial_inbox[loser_key]["last_error"]).lower()

        await refund_connection.execute(
            "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
            "WHERE message_key = ?",
            (loser_key,),
        )
        await refund_connection.commit()
        if first_winner == "payment":
            retry_result = await _attempt_refund_query(refund_service)
        else:
            retry_result = await _attempt_payment_query(payment_service)
        assert retry_result[0] == "ok"

        duplicate_payment = await _attempt_payment_query(payment_service)
        await payment_handle.commit()
        duplicate_refund = await _attempt_refund_query(refund_service)
        await refund_handle.commit()
        assert duplicate_payment[0] == "ok"
        assert duplicate_payment[1].get("paymentStatus") == "paid"
        assert duplicate_refund == (
            "ok",
            {"duplicate": True, "kind": "duplicate"},
        )

        state = await _read_final_state(payment_connection)
        _assert_common_final_state(state, first_winner)
        if first_winner == "payment":
            _assert_payment_first_assets(state)
        else:
            _assert_refund_first_assets(state)
    finally:
        await close_db(refund_connection)
        await close_db(payment_connection)
