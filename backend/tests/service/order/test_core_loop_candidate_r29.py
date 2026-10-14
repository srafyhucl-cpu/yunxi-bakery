"""MiniApp 核心闭环 r29：微信支付与退款通知并发事实保留。"""

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
from app.service.order.payment_runtime import OrderPaymentRuntimeService

ORDER_ID = "order_payment_refund_notify_race_001"
USER_ID = "wx_payment_refund_notify_race_001"
OPENID = "openid_payment_refund_notify_race_001"
MOBILE = "13800002929"
ORDER_AMOUNT_FEN = 19_800
TRANSACTION_ID = "4200000000202609250029001"
REFUND_NO = "R-payment-refund-notify-race-001"
PAYMENT_EVENT_ID = "EV-payment-refund-notify-race-001"
REFUND_EVENT_ID = "EV-refund-payment-notify-race-001"
PAYMENT_KEY = f"wechat_pay_notify:{PAYMENT_EVENT_ID}"
REFUND_KEY = f"wechat_pay_notify:{REFUND_EVENT_ID}"


def _build_runtime_service(handle: DatabaseHandle) -> OrderPaymentRuntimeService:
    """构建真实微信支付与退款通知入口。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        event_repo=OrderEventRepo(handle),
    )


async def _seed_order(connection: aiosqlite.Connection) -> None:
    """写入待支付合成订单、会员身份和零资产账户。"""
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id, status) "
        "VALUES (?, 'miniapp', ?, 'active')",
        (f"session_{ORDER_ID}", USER_ID),
    )
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '支付退款竞态会员', 'high', 1)",
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
        "VALUES (?, 0, 0)",
        (MOBILE,),
    )
    await connection.execute(
        "INSERT INTO orders (id, session_id, channel, user_id, products, "
        "total_amount, delivery, payment, status, created_at, updated_at) "
        "VALUES (?, ?, 'miniapp', ?, ?, ?, ?, ?, 'pending', ?, ?)",
        (
            ORDER_ID,
            f"session_{ORDER_ID}",
            USER_ID,
            json.dumps(
                [
                    {
                        "product_id": "p_payment_refund_race",
                        "title": "支付退款竞态蛋糕",
                        "price_fen": ORDER_AMOUNT_FEN,
                        "quantity": 1,
                        "inventory_reserved": False,
                    }
                ],
                ensure_ascii=False,
            ),
            ORDER_AMOUNT_FEN / 100,
            json.dumps({}, ensure_ascii=False),
            json.dumps(
                {
                    "status": "unpaid",
                    "method": "",
                    "couponFen": 0,
                    "balanceFen": 0,
                    "pointsFen": 0,
                    "pointsUsed": 0,
                    "createdAt": "2026-09-25 11:00:00",
                },
                ensure_ascii=False,
            ),
            "2026-09-25 11:00:00",
            "2026-09-25 11:00:00",
        ),
    )
    await connection.commit()


def _payment_transaction() -> dict:
    """构造同一微信交易的支付成功通知。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": "mch-payment-refund-race",
        "appid": "appid-payment-refund-race",
        "amount": {"total": ORDER_AMOUNT_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T11:10:00+08:00",
    }


def _refund_transaction() -> dict:
    """构造同一微信交易的全额退款成功通知。"""
    return {
        "mchid": "mch-payment-refund-race",
        "out_trade_no": ORDER_ID,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": REFUND_NO,
        "refund_id": f"wx-{REFUND_NO}",
        "refund_status": "SUCCESS",
        "success_time": "2026-09-25T11:12:00+08:00",
        "amount": {
            "total": ORDER_AMOUNT_FEN,
            "refund": ORDER_AMOUNT_FEN,
            "payer_total": ORDER_AMOUNT_FEN,
            "payer_refund": ORDER_AMOUNT_FEN,
        },
    }


def _notify_body(event_id: str, kind: str) -> bytes:
    """构造仅区分支付与退款资源的通知外层载荷。"""
    return json.dumps(
        {
            "id": event_id,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {"kind": kind},
        },
        ensure_ascii=False,
    ).encode("utf-8")


async def _attempt_payment_notify(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, dict | str]:
    """执行支付通知并区分业务冲突与瞬时锁冲突。"""
    try:
        result = await service.handle_wechat_payment_notify(
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


async def _attempt_refund_notify(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, dict | str]:
    """执行退款通知并区分业务冲突与瞬时锁冲突。"""
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


@pytest.mark.asyncio
async def test_payment_and_refund_notify_race_preserves_ledgers(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """并发通知只能产生一笔支付、退款和资产补偿事实。"""
    database_path = tmp_path / "payment-refund-notify-race.db"
    payment_connection = await init_db(str(database_path))
    refund_connection = await init_db(str(database_path))
    payment_handle = DatabaseHandle(payment_connection)
    refund_handle = DatabaseHandle(refund_connection)
    try:
        await _seed_order(payment_connection)
        payment_service = _build_runtime_service(payment_handle)
        refund_service = _build_runtime_service(refund_handle)
        monkeypatch.setattr(
            settings,
            "WECHAT_PAY_MCH_ID",
            "mch-payment-refund-race",
        )
        monkeypatch.setattr(
            settings,
            "WECHAT_MINIAPP_APP_ID",
            "appid-payment-refund-race",
        )
        payment_transaction = _payment_transaction()
        refund_transaction = _refund_transaction()
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_verify_wechat_notify_signature",
            lambda self, raw_body, headers: True,
        )

        def decrypt_resource(self, resource: dict) -> dict:
            """按测试资源类型返回对应已解密事务。"""
            if resource.get("kind") == "payment":
                return payment_transaction
            return refund_transaction

        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_decrypt_wechat_resource",
            decrypt_resource,
        )
        payment_body = _notify_body(PAYMENT_EVENT_ID, "payment")
        refund_body = _notify_body(REFUND_EVENT_ID, "refund")

        both_snapshots_read = asyncio.Event()
        observed_handles: set[int] = set()
        payment_handle_key = id(payment_handle)
        refund_handle_key = id(refund_handle)
        original_get_order = OrderRepo.get_order

        async def read_old_snapshot_together(
            repo: OrderRepo,
            order_id: str,
        ):
            """让两个业务事务都读到未支付且未退款的旧快照。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if order_id == ORDER_ID and handle_key in {
                payment_handle_key,
                refund_handle_key,
            }:
                observed_handles.add(handle_key)
                if len(observed_handles) == 2:
                    both_snapshots_read.set()
                if len(observed_handles) <= 2:
                    await asyncio.wait_for(both_snapshots_read.wait(), timeout=5)
            return order

        monkeypatch.setattr(OrderRepo, "get_order", read_old_snapshot_together)

        async def run_payment() -> tuple[str, dict | str]:
            """运行真实支付通知。"""
            return await _attempt_payment_notify(payment_service, payment_body)

        async def run_refund() -> tuple[str, dict | str]:
            """运行真实退款通知。"""
            return await _attempt_refund_notify(refund_service, refund_body)

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
        winner_key = PAYMENT_KEY if payment_result[0] == "ok" else REFUND_KEY
        failed_key = REFUND_KEY if winner_key == PAYMENT_KEY else PAYMENT_KEY

        assert observed_handles == {payment_handle_key, refund_handle_key}
        assert sorted((result[0] for result in (payment_result, refund_result))) == [
            "locked",
            "ok",
        ]
        assert str(initial_inbox[winner_key]["status"]) == "processed"
        assert int(initial_inbox[winner_key]["attempt_count"]) == 1
        assert str(initial_inbox[failed_key]["status"]) == "failed"
        assert int(initial_inbox[failed_key]["attempt_count"]) == 1
        assert "locked" in str(initial_inbox[failed_key]["last_error"]).lower()

        await refund_connection.execute(
            "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
            "WHERE message_key = ?",
            (failed_key,),
        )
        await refund_connection.commit()
        if failed_key == PAYMENT_KEY:
            retry_result = await _attempt_payment_notify(payment_service, payment_body)
        else:
            retry_result = await _attempt_refund_notify(refund_service, refund_body)
        assert retry_result[0] == "ok"

        duplicate_payment = await _attempt_payment_notify(payment_service, payment_body)
        await payment_handle.commit()
        duplicate_refund = await _attempt_refund_notify(refund_service, refund_body)
        await refund_handle.commit()
        assert duplicate_payment == (
            "ok",
            {"duplicate": True},
        )
        assert duplicate_refund == (
            "ok",
            {"duplicate": True, "kind": "duplicate"},
        )

        order_rows = await refund_connection.execute_fetchall(
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        )
        payment_rows = await refund_connection.execute_fetchall(
            "SELECT order_id FROM payment_transactions "
            "WHERE transaction_id = ? ORDER BY order_id",
            (TRANSACTION_ID,),
        )
        refund_rows = await refund_connection.execute_fetchall(
            "SELECT out_refund_no, order_id, transaction_id, payer_refund_fen "
            "FROM wechat_refund_events WHERE out_refund_no = ?",
            (REFUND_NO,),
        )
        order_event_rows = await refund_connection.execute_fetchall(
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        )
        inbox_rows = await refund_connection.execute_fetchall(
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key IN (?, ?) ORDER BY message_key",
            (PAYMENT_KEY, REFUND_KEY),
        )
        points_rows = await refund_connection.execute_fetchall(
            "SELECT unique_id, event_type, amount FROM points_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        )
        ledger_operation_rows = await refund_connection.execute_fetchall(
            "SELECT unique_id, operation_type FROM ledger_operation "
            "WHERE subject_id = ? ORDER BY id",
            (ORDER_ID,),
        )
        refund_operation_rows = await refund_connection.execute_fetchall(
            "SELECT operation_key, status, clawback_amount FROM refund_operation "
            "WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        )
        member_rows = await refund_connection.execute_fetchall(
            "SELECT stored_value_fen, points FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        )
        reconcile_rows = await refund_connection.execute_fetchall(
            "SELECT unique_id FROM points_refund_reconcile WHERE order_id = ?",
            (ORDER_ID,),
        )
        balance_rows = await refund_connection.execute_fetchall(
            "SELECT unique_id FROM balance_ledger WHERE biz_id = ?",
            (ORDER_ID,),
        )
        coupon_rows = await refund_connection.execute_fetchall(
            "SELECT coupon_id, status FROM coupon_inventory WHERE order_no = ?",
            (ORDER_ID,),
        )
        payment = json.loads(str(order_rows[0]["payment"]))

        assert str(order_rows[0]["status"]) == "pending"
        assert str(payment["status"]) == "paid"
        assert str(payment["method"]) == "wechat"
        assert str(payment["transactionId"]) == TRANSACTION_ID
        assert str(payment["refundStatus"]) == "full"
        assert int(payment["refundFen"]) == ORDER_AMOUNT_FEN
        assert [dict(row) for row in payment_rows] == [{"order_id": ORDER_ID}]
        assert [dict(row) for row in refund_rows] == [
            {
                "out_refund_no": REFUND_NO,
                "order_id": ORDER_ID,
                "transaction_id": TRANSACTION_ID,
                "payer_refund_fen": ORDER_AMOUNT_FEN,
            }
        ]
        assert [(row["status"], row["operator"]) for row in order_event_rows] == [
            ("paid", "wechat-pay")
        ]
        assert {str(row["message_key"]): str(row["status"]) for row in inbox_rows} == {
            PAYMENT_KEY: "processed",
            REFUND_KEY: "processed",
        }
        assert sorted(int(row["attempt_count"]) for row in inbox_rows) == [1, 2]

        if points_rows:
            assert [str(row["event_type"]) for row in points_rows] == [
                "order_award",
                "order_refund",
            ]
            assert [int(row["amount"]) for row in points_rows] == [198, -198]
            assert [str(row["operation_type"]) for row in ledger_operation_rows] == [
                "settle_award",
                "refund_clawback",
            ]
            assert [dict(row) for row in refund_operation_rows] == [
                {
                    "operation_key": f"points:refund:{ORDER_ID}",
                    "status": "succeeded",
                    "clawback_amount": 198,
                }
            ]
        else:
            assert points_rows == []
            assert ledger_operation_rows == []
            assert refund_operation_rows == []

        point_unique_ids = [str(row["unique_id"]) for row in points_rows]
        ledger_unique_ids = [str(row["unique_id"]) for row in ledger_operation_rows]
        assert len(point_unique_ids) == len(set(point_unique_ids))
        assert len(ledger_unique_ids) == len(set(ledger_unique_ids))
        assert [dict(row) for row in member_rows] == [
            {"stored_value_fen": 0, "points": 0}
        ]
        assert reconcile_rows == []
        assert balance_rows == []
        assert coupon_rows == []
    finally:
        await close_db(refund_connection)
        await close_db(payment_connection)
