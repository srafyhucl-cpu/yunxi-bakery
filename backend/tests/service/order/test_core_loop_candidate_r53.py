"""MiniApp 核心闭环 r53：部分退款转超额退款与后台关单并发复核。"""

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
from app.service.order.refund_notification import WechatRefundNotificationService
from app.service.order.wechat_normalizers import RefundNotify
from tests.service.order.test_core_loop_candidate_r51 import (
    BALANCE_PAY_FEN,
    INITIAL_BALANCE_FEN,
    ITEM_ID,
    MOBILE,
    ORDER_AMOUNT_FEN,
    ORDER_ID,
    USER_ID,
    _admin_cancel_service,
    _seed_partial_order,
)

EXTERNAL_FEN = ORDER_AMOUNT_FEN - BALANCE_PAY_FEN
REFUND_FEN = 5_000
TOTAL_REFUND_FEN = REFUND_FEN * 2
EXPECTED_AWARD_POINTS = EXTERNAL_FEN // 100
TRANSACTION_ID = "4200000000202609251234567953"
MCH_ID = "mch-over-refund-admin-cancel-race-r53"
APP_ID = "appid-over-refund-admin-cancel-race-r53"
PARTIAL_REFUND_NO = "R-over-refund-admin-cancel-race-r53-partial"
OVER_REFUND_NO = "R-over-refund-admin-cancel-race-r53-over"
OVER_REFUND_EVENT = "EV-over-refund-admin-cancel-race-r53-over"
OVER_REFUND_KEY = f"wechat_pay_notify:{OVER_REFUND_EVENT}"


class _LocalWechatPay:
    """为支付查询和退款通知提供不触网的本地微信集成。"""

    def is_ready(self) -> bool:
        return False

    def format_success_time(self, value: str) -> str:
        return "2026-09-25 16:00:00"


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
        "success_time": "2026-09-25T16:00:00+08:00",
    }


def _partial_refund_notify() -> RefundNotify:
    """构造第一笔 5,000 分部分退款事实。"""
    return RefundNotify(
        mchid=MCH_ID,
        out_trade_no=ORDER_ID,
        transaction_id=TRANSACTION_ID,
        out_refund_no=PARTIAL_REFUND_NO,
        refund_id=f"wx-{PARTIAL_REFUND_NO}",
        refund_status="SUCCESS",
        success_time="2026-09-25T16:05:00+08:00",
        total_fen=EXTERNAL_FEN,
        refund_fen=REFUND_FEN,
        payer_total_fen=EXTERNAL_FEN,
        payer_refund_fen=REFUND_FEN,
        user_received_account="微信支付",
    )


def _over_refund_transaction() -> dict:
    """构造第二笔使累计退款超过微信实付的退款事实。"""
    return {
        "mchid": MCH_ID,
        "out_trade_no": ORDER_ID,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": OVER_REFUND_NO,
        "refund_id": f"wx-{OVER_REFUND_NO}",
        "refund_status": "SUCCESS",
        "success_time": "2026-09-25T16:10:00+08:00",
        "amount": {
            "total": EXTERNAL_FEN,
            "refund": REFUND_FEN,
            "payer_total": EXTERNAL_FEN,
            "payer_refund": REFUND_FEN,
        },
    }


def _notify_body() -> bytes:
    """构造第二笔退款的本地通知外层载荷。"""
    return json.dumps(
        {
            "id": OVER_REFUND_EVENT,
            "event_type": "REFUND.SUCCESS",
            "resource": {
                "kind": "refund",
                "order_id": ORDER_ID,
                "out_refund_no": OVER_REFUND_NO,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")


async def _attempt_admin_cancel(service) -> tuple[str, str]:
    """在独立生产事务中执行真实后台取消入口。"""
    try:
        async with service._order_repo.transaction():
            result = await service.update_admin_order_status(ORDER_ID, "cancelled")
        return "ok", str(result["status"])
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_refund_notify(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, dict | str]:
    """执行真实退款通知入口并区分业务结果与瞬时锁失败。"""
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


async def _read_final_state(
    connection: aiosqlite.Connection,
) -> dict[str, list[dict]]:
    """读取订单、库存、退款、资产、案件和事件最终事实。"""
    queries = {
        "orders": (
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        ),
        "products": (
            "SELECT stock FROM youzan_products WHERE item_id = ?",
            (str(ITEM_ID),),
        ),
        "transactions": (
            "SELECT transaction_id, order_id FROM payment_transactions "
            "WHERE transaction_id = ?",
            (TRANSACTION_ID,),
        ),
        "refunds": (
            "SELECT out_refund_no, payer_refund_fen, source FROM wechat_refund_events "
            "WHERE order_id = ? ORDER BY out_refund_no",
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
            "SELECT operation_key, status, clawback_amount FROM refund_operation "
            "WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "cases": (
            "SELECT unique_id, amount, status FROM points_refund_reconcile "
            "WHERE order_id = ? ORDER BY unique_id",
            (ORDER_ID,),
        ),
        "events": (
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "inbox": (
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key = ?",
            (OVER_REFUND_KEY,),
        ),
    }
    return {
        name: await connection.execute_fetchall(sql, parameters)
        for name, (sql, parameters) in queries.items()
    }


def _assert_final_state(state: dict[str, list[dict]]) -> None:
    """断言后台只关单一次，且超额退款不产生任何资产补偿。"""
    assert len(state["orders"]) == 1
    assert str(state["orders"][0]["status"]) == "cancelled"
    payment = json.loads(str(state["orders"][0]["payment"]))
    assert payment["status"] == "paid"
    assert payment["method"] == "combined"
    assert payment["transactionId"] == TRANSACTION_ID
    assert int(payment["balanceFen"]) == BALANCE_PAY_FEN
    assert int(payment["externalPaidFen"]) == EXTERNAL_FEN
    assert int(payment["pointsAwarded"]) == EXPECTED_AWARD_POINTS
    assert payment["refundStatus"] == "over"
    assert int(payment["refundFen"]) == TOTAL_REFUND_FEN

    assert [dict(row) for row in state["products"]] == [{"stock": 1}]
    assert [dict(row) for row in state["transactions"]] == [
        {"transaction_id": TRANSACTION_ID, "order_id": ORDER_ID}
    ]
    assert [dict(row) for row in state["refunds"]] == [
        {
            "out_refund_no": OVER_REFUND_NO,
            "payer_refund_fen": REFUND_FEN,
            "source": "notify",
        },
        {
            "out_refund_no": PARTIAL_REFUND_NO,
            "payer_refund_fen": REFUND_FEN,
            "source": "notify",
        },
    ]
    assert [dict(row) for row in state["members"]] == [
        {
            "stored_value_fen": INITIAL_BALANCE_FEN - BALANCE_PAY_FEN,
            "points": EXPECTED_AWARD_POINTS,
        }
    ]
    assert [dict(row) for row in state["balance_ledger"]] == [
        {
            "unique_id": f"combined_pay:{ORDER_ID}",
            "amount_fen": -BALANCE_PAY_FEN,
            "balance_after_fen": INITIAL_BALANCE_FEN - BALANCE_PAY_FEN,
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
    assert state["refund_operations"] == []
    assert {str(row["unique_id"]) for row in state["cases"]} == {
        f"refund:partial:{PARTIAL_REFUND_NO}",
        f"refund:over_refund:{OVER_REFUND_NO}",
    }
    assert [dict(row) for row in state["events"]] == [
        {"status": "pending", "operator": f"miniapp:{USER_ID}"},
        {"status": "paid", "operator": "wechat-pay"},
        {"status": "cancelled", "operator": "admin"},
    ]
    assert [dict(row) for row in state["inbox"]] == [
        {"message_key": OVER_REFUND_KEY, "status": "processed", "attempt_count": 1}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["refund", "admin"])
async def test_over_refund_and_admin_cancel_race_preserves_assets(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    first_winner: str,
) -> None:
    """超额退款与后台关单并发后只能安全关单，不能重复补偿资产。"""
    database_path = tmp_path / f"over-refund-admin-cancel-{first_winner}-r53.db"
    refund_connection = await init_db(str(database_path))
    admin_connection = await init_db(str(database_path))
    refund_handle = DatabaseHandle(refund_connection)
    admin_handle = DatabaseHandle(admin_connection)
    try:
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        await _seed_partial_order(refund_connection)

        refund_service = _runtime_service(refund_handle)
        paid = await refund_service.reconcile_pay_from_query(_payment_query())
        assert paid["paymentStatus"] == "paid"
        partial = await WechatRefundNotificationService(
            OrderRepo(refund_handle)
        ).apply_refund_notify(_partial_refund_notify())
        assert partial["kind"] == "acknowledged"
        assert partial["accumulatedFen"] == REFUND_FEN

        admin_service = _admin_cancel_service(admin_handle)
        raw_body = _notify_body()
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_verify_wechat_notify_signature",
            lambda self, payload, headers: True,
        )
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_decrypt_wechat_resource",
            lambda self, resource: _over_refund_transaction(),
        )

        refund_first_read_barrier = asyncio.Barrier(2)
        admin_first_snapshot_read = asyncio.Event()
        admin_first_attempt_completed = asyncio.Event()
        winner_committed = asyncio.Event()
        first_read_handles: set[int] = set()
        refund_snapshot_handles: set[int] = set()
        refund_handle_key = id(refund_handle)
        admin_handle_key = id(admin_handle)
        original_claim_notify = notify_intake.claim_notify
        original_get_order = OrderRepo.get_order

        async def commit_refund_claim_before_business(
            db,
            event_id: str,
            payload: dict | None = None,
            *,
            lease_seconds: int = notify_intake.DEFAULT_NOTIFY_LEASE_SECONDS,
        ) -> dict:
            """先提交退款 inbox claim，避免认领写锁遮挡后台首胜顺序。"""
            claim = await original_claim_notify(
                db,
                event_id,
                payload,
                lease_seconds=lease_seconds,
            )
            await db.commit()
            return claim

        async def synchronized_partial_snapshot_read(
            repo: OrderRepo,
            order_id: str,
        ):
            """按参数固定后台先判定或双方旧快照竞争的时序。"""
            handle_key = id(repo._db)
            if order_id != ORDER_ID or handle_key in first_read_handles:
                return await original_get_order(repo, order_id)
            first_read_handles.add(handle_key)
            if first_winner == "admin":
                if handle_key == admin_handle_key:
                    admin_first_snapshot_read.set()
                    return await original_get_order(repo, order_id)
                await asyncio.wait_for(admin_first_snapshot_read.wait(), timeout=5)
                await asyncio.wait_for(winner_committed.wait(), timeout=5)
                return await original_get_order(repo, order_id)

            order = await original_get_order(repo, order_id)
            if handle_key not in refund_snapshot_handles:
                refund_snapshot_handles.add(handle_key)
                await asyncio.wait_for(refund_first_read_barrier.wait(), timeout=5)
                role = "refund" if handle_key == refund_handle_key else "admin"
                if role == "admin":
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(
            OrderRepo,
            "get_order",
            synchronized_partial_snapshot_read,
        )
        monkeypatch.setattr(
            notify_intake,
            "claim_notify",
            commit_refund_claim_before_business,
        )

        async def run_refund() -> tuple[str, dict | str]:
            if first_winner == "admin":
                await asyncio.wait_for(admin_first_attempt_completed.wait(), timeout=5)
            result = await _attempt_refund_notify(refund_service, raw_body)
            if first_winner == "refund":
                winner_committed.set()
            return result

        async def run_admin() -> tuple[str, str]:
            result = await _attempt_admin_cancel(admin_service)
            if first_winner == "admin":
                winner_committed.set()
                admin_first_attempt_completed.set()
            return result

        refund_result, admin_result = await asyncio.gather(run_refund(), run_admin())
        assert first_read_handles == {refund_handle_key, admin_handle_key}
        assert refund_result[0] == "ok"
        assert isinstance(refund_result[1], dict)
        assert refund_result[1]["kind"] == "rejected_recorded"
        if first_winner == "refund":
            assert admin_result[0] == "locked"
        else:
            assert admin_result[0] == "conflict"
            assert admin_result[1] == "已支付订单不允许取消"

        monkeypatch.setattr(notify_intake, "claim_notify", original_claim_notify)
        monkeypatch.setattr(OrderRepo, "get_order", original_get_order)
        retry_result = await _attempt_admin_cancel(admin_service)
        assert retry_result == ("ok", "cancelled")

        duplicate_refund = await _attempt_refund_notify(refund_service, raw_body)
        assert duplicate_refund == ("ok", {"duplicate": True, "kind": "duplicate"})

        state = await _read_final_state(refund_connection)
        _assert_final_state(state)
    finally:
        await close_db(admin_connection)
        await close_db(refund_connection)
