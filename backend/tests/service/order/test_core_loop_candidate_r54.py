"""MiniApp 核心闭环 r54：部分退款与支付结算并发候选复核。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.repository.base import DatabaseHandle
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.order import notify_intake
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.wechat_normalizers import RefundNotify
from tests.service.order.test_core_loop_candidate_r51 import (
    BALANCE_PAY_FEN,
    INITIAL_BALANCE_FEN,
    MOBILE,
    ORDER_AMOUNT_FEN,
    ORDER_ID,
    USER_ID,
    _seed_partial_order,
)

EXTERNAL_FEN = ORDER_AMOUNT_FEN - BALANCE_PAY_FEN
REFUND_FEN = 2_000
EXPECTED_AWARD_POINTS = EXTERNAL_FEN // 100
TRANSACTION_ID = "4200000000202609251234567954"
MCH_ID = "mch-partial-refund-payment-race-r54"
APP_ID = "appid-partial-refund-payment-race-r54"
REFUND_NO = "R-partial-refund-payment-race-r54"
EVENT_ID = "EV-partial-refund-payment-race-r54"
REFUND_KEY = f"wechat_pay_notify:{EVENT_ID}"
PAYMENT_KEY = f"wechat_pay_notify:query:pay:{ORDER_ID}:{TRANSACTION_ID}"


class _LocalWechatPay:
    """为支付查询和退款通知提供不触网的本地微信集成。"""

    def is_ready(self) -> bool:
        return False

    def format_success_time(self, value: str) -> str:
        return "2026-09-25 17:00:00"


def _runtime_service(handle: DatabaseHandle) -> OrderPaymentRuntimeService:
    """构建真实支付查询与退款通知入口。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=_LocalWechatPay(),
        event_repo=OrderEventRepo(handle),
    )


def _payment_query() -> dict:
    """构造组合支付外部腿支付成功查询。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": MCH_ID,
        "appid": APP_ID,
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T17:00:00+08:00",
    }


def _partial_refund_notify() -> RefundNotify:
    """构造一笔 2,000 分的部分退款事实。"""
    return RefundNotify(
        mchid=MCH_ID,
        out_trade_no=ORDER_ID,
        transaction_id=TRANSACTION_ID,
        out_refund_no=REFUND_NO,
        refund_id=f"wx-{REFUND_NO}",
        refund_status="SUCCESS",
        success_time="2026-09-25T17:05:00+08:00",
        total_fen=EXTERNAL_FEN,
        refund_fen=REFUND_FEN,
        payer_total_fen=EXTERNAL_FEN,
        payer_refund_fen=REFUND_FEN,
        user_received_account="微信支付",
    )


def _notify_body() -> bytes:
    """构造部分退款通知外层载荷。"""
    return json.dumps(
        {
            "id": EVENT_ID,
            "event_type": "REFUND.SUCCESS",
            "resource": {
                "kind": "refund",
                "order_id": ORDER_ID,
                "out_refund_no": REFUND_NO,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")


async def _attempt_payment(
    service: OrderPaymentRuntimeService,
) -> tuple[str, dict | str]:
    """执行支付查询恢复并区分业务冲突与瞬时锁失败。"""
    try:
        result = await service.reconcile_pay_from_query(_payment_query())
        return "ok", result
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_refund(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, dict | str]:
    """执行退款通知并区分业务冲突与瞬时锁失败。"""
    try:
        result = await service.handle_wechat_refund_notify(
            raw_body=raw_body,
            headers={},
        )
        return "ok", result
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _read_state(connection: aiosqlite.Connection) -> dict[str, list[dict]]:
    """读取支付、退款、资产、事件和 inbox 的最终事实。"""
    queries = {
        "orders": (
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        ),
        "transactions": (
            "SELECT transaction_id, order_id FROM payment_transactions "
            "WHERE transaction_id = ?",
            (TRANSACTION_ID,),
        ),
        "refunds": (
            "SELECT out_refund_no, payer_refund_fen, source FROM wechat_refund_events "
            "WHERE order_id = ?",
            (ORDER_ID,),
        ),
        "members": (
            "SELECT stored_value_fen, points FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        ),
        "balance_ledger": (
            "SELECT unique_id, amount_fen FROM balance_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "points_ledger": (
            "SELECT unique_id, event_type, amount, total FROM points_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "events": (
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "inbox": (
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key IN (?, ?)",
            (PAYMENT_KEY, REFUND_KEY),
        ),
    }
    return {
        name: await connection.execute_fetchall(sql, parameters)
        for name, (sql, parameters) in queries.items()
    }


def _assert_common_state(
    state: dict[str, list[dict]],
    *,
    payment_settled: bool,
    first_winner: str,
) -> None:
    """断言部分退款事实和组合支付资产不会被并发结算丢失。"""
    assert len(state["orders"]) == 1
    payment = json.loads(str(state["orders"][0]["payment"]))
    assert str(state["orders"][0]["status"]) == "pending"
    assert payment["status"] == ("paid" if payment_settled else "partial")
    assert payment["method"] == "combined"
    if payment_settled:
        assert payment["transactionId"] == TRANSACTION_ID
    assert int(payment["balanceFen"]) == BALANCE_PAY_FEN
    assert int(payment["externalPaidFen"]) == EXTERNAL_FEN
    assert payment["refundStatus"] == "partial"
    assert int(payment["refundFen"]) == REFUND_FEN
    assert int(payment.get("pointsAwarded", 0)) == (
        EXPECTED_AWARD_POINTS if payment_settled else 0
    )
    assert [dict(row) for row in state["transactions"]] == [
        {"transaction_id": TRANSACTION_ID, "order_id": ORDER_ID}
    ]
    assert [dict(row) for row in state["refunds"]] == [
        {
            "out_refund_no": REFUND_NO,
            "payer_refund_fen": REFUND_FEN,
            "source": "notify",
        }
    ]
    assert [dict(row) for row in state["members"]] == [
        {
            "stored_value_fen": INITIAL_BALANCE_FEN - BALANCE_PAY_FEN,
            "points": EXPECTED_AWARD_POINTS if payment_settled else 0,
        }
    ]
    assert [dict(row) for row in state["balance_ledger"]] == [
        {
            "unique_id": f"combined_pay:{ORDER_ID}",
            "amount_fen": -BALANCE_PAY_FEN,
        }
    ]
    if payment_settled:
        assert [dict(row) for row in state["points_ledger"]] == [
            {
                "unique_id": f"points:award:{ORDER_ID}",
                "event_type": "order_award",
                "amount": EXPECTED_AWARD_POINTS,
                "total": EXPECTED_AWARD_POINTS,
            }
        ]
        assert [dict(row) for row in state["events"]] == [
            {"status": "pending", "operator": f"miniapp:{USER_ID}"},
            {"status": "paid", "operator": "wechat-pay"},
        ]
    else:
        assert state["points_ledger"] == []
        assert [dict(row) for row in state["events"]] == [
            {"status": "pending", "operator": f"miniapp:{USER_ID}"},
        ]
    assert {
        str(row["message_key"]): (str(row["status"]), int(row["attempt_count"]))
        for row in state["inbox"]
    } == {
        PAYMENT_KEY: ("processed", 1 if first_winner == "payment" else 2),
        REFUND_KEY: ("processed", 1 if first_winner == "refund" else 2),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["payment", "refund"])
async def test_partial_refund_and_payment_settlement_race_preserves_refund_fact(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    first_winner: str,
) -> None:
    """部分退款与支付结算并发后只能保留一次退款事实和一次积分发放。"""
    database_path = tmp_path / f"partial-refund-payment-{first_winner}-r54.db"
    payment_connection = await init_db(str(database_path))
    refund_connection = await init_db(str(database_path))
    payment_handle = DatabaseHandle(payment_connection)
    refund_handle = DatabaseHandle(refund_connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        await _seed_partial_order(payment_connection)
        payment_service = _runtime_service(payment_handle)
        refund_service = _runtime_service(refund_handle)
        raw_body = _notify_body()
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_verify_wechat_notify_signature",
            lambda self, payload, headers: True,
        )
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_decrypt_wechat_resource",
            lambda self, resource: {
                "mchid": MCH_ID,
                "out_trade_no": ORDER_ID,
                "transaction_id": TRANSACTION_ID,
                "out_refund_no": REFUND_NO,
                "refund_id": f"wx-{REFUND_NO}",
                "refund_status": "SUCCESS",
                "success_time": "2026-09-25T17:05:00+08:00",
                "amount": {
                    "total": EXTERNAL_FEN,
                    "refund": REFUND_FEN,
                    "payer_total": EXTERNAL_FEN,
                    "payer_refund": REFUND_FEN,
                },
            },
        )

        both_claims_committed = asyncio.Event()
        committed_claims = 0
        original_claim_notify = notify_intake.claim_notify
        original_claim_notify_key = notify_intake.claim_notify_key

        async def commit_notify_claim_before_business(
            db,
            event_id: str,
            payload: dict | None = None,
            *,
            lease_seconds: int = notify_intake.DEFAULT_NOTIFY_LEASE_SECONDS,
        ) -> dict:
            """先提交退款 inbox claim，避免认领写锁改变业务顺序。"""
            nonlocal committed_claims
            claim = await original_claim_notify(
                db,
                event_id,
                payload,
                lease_seconds=lease_seconds,
            )
            await db.commit()
            committed_claims += 1
            if committed_claims == 2:
                both_claims_committed.set()
            await asyncio.wait_for(both_claims_committed.wait(), timeout=5)
            return claim

        async def commit_notify_key_before_business(
            db,
            message_key: str,
            payload: dict | None = None,
            *,
            lease_seconds: int = notify_intake.DEFAULT_NOTIFY_LEASE_SECONDS,
        ) -> dict:
            """先提交支付查询 inbox claim，避免认领写锁改变业务顺序。"""
            nonlocal committed_claims
            claim = await original_claim_notify_key(
                db,
                message_key,
                payload,
                lease_seconds=lease_seconds,
            )
            await db.commit()
            committed_claims += 1
            if committed_claims == 2:
                both_claims_committed.set()
            await asyncio.wait_for(both_claims_committed.wait(), timeout=5)
            return claim

        monkeypatch.setattr(
            notify_intake, "claim_notify", commit_notify_claim_before_business
        )
        monkeypatch.setattr(
            notify_intake,
            "claim_notify_key",
            commit_notify_key_before_business,
        )

        payment_mark_snapshot_ready = asyncio.Event()
        payment_first_winner_committed = asyncio.Event()
        refund_first_winner_committed = asyncio.Event()
        original_get_order = OrderRepo.get_order
        payment_get_order_count = 0
        refund_get_order_count = 0

        async def synchronize_payment_and_refund_snapshot(
            repo: OrderRepo,
            order_id: str,
        ):
            """让支付 mark_paid 和退款都先拿到同一份 partial 快照。"""
            nonlocal payment_get_order_count, refund_get_order_count
            if order_id != ORDER_ID:
                return await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            order = await original_get_order(repo, order_id)
            if handle_key == id(payment_handle):
                payment_get_order_count += 1
                if payment_get_order_count == 3:
                    payment_mark_snapshot_ready.set()
                    if first_winner == "refund":
                        await asyncio.wait_for(
                            refund_first_winner_committed.wait(), timeout=5
                        )
            else:
                refund_get_order_count += 1
                if first_winner == "payment":
                    await asyncio.wait_for(
                        payment_first_winner_committed.wait(), timeout=5
                    )
                else:
                    await asyncio.wait_for(
                        payment_mark_snapshot_ready.wait(), timeout=5
                    )
            return order

        monkeypatch.setattr(
            OrderRepo,
            "get_order",
            synchronize_payment_and_refund_snapshot,
        )

        async def run_payment() -> tuple[str, dict | str]:
            result = await _attempt_payment(payment_service)
            if first_winner == "payment":
                payment_first_winner_committed.set()
            return result

        async def run_refund() -> tuple[str, dict | str]:
            result = await _attempt_refund(refund_service, raw_body)
            if first_winner == "refund":
                refund_first_winner_committed.set()
            return result

        payment_result, refund_result = await asyncio.gather(
            run_payment(),
            run_refund(),
        )
        winner_result = payment_result if first_winner == "payment" else refund_result
        loser_result = refund_result if first_winner == "payment" else payment_result
        assert winner_result[0] == "ok"
        assert loser_result[0] in {"conflict", "locked"}
        assert payment_get_order_count >= 3
        assert refund_get_order_count >= 1

        if loser_result[0] != "ok":
            if first_winner == "payment":
                await refund_connection.execute(
                    "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
                    "WHERE message_key = ?",
                    (REFUND_KEY,),
                )
                await refund_connection.commit()
                retry = await _attempt_refund(refund_service, raw_body)
            else:
                await payment_connection.execute(
                    "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
                    "WHERE message_key = ?",
                    (PAYMENT_KEY,),
                )
                await payment_connection.commit()
                retry = await _attempt_payment(payment_service)
            assert retry[0] == "ok"

        duplicate_refund = await _attempt_refund(refund_service, raw_body)
        assert duplicate_refund == ("ok", {"duplicate": True, "kind": "duplicate"})
        state = await _read_state(payment_connection)
        _assert_common_state(
            state,
            payment_settled=True,
            first_winner=first_winner,
        )
    finally:
        await close_db(refund_connection)
        await close_db(payment_connection)
