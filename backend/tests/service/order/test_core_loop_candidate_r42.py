"""MiniApp 核心闭环 r42：退款通知与查询恢复并发候选复核。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.models.order import Order, OrderStatus
from app.repository.base import DatabaseHandle
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.order.payment_runtime import OrderPaymentRuntimeService

ORDER_ID = "order_refund_notify_query_race_r42_001"
USER_ID = "wx_refund_notify_query_race_r42_001"
OPENID = "refund_notify_query_race_r42_001"
MOBILE = "13800003042"
ORDER_AMOUNT_FEN = 10_000
BALANCE_FEN = 2_000
EXTERNAL_FEN = ORDER_AMOUNT_FEN - BALANCE_FEN
INITIAL_BALANCE_FEN = 20_000
TRANSACTION_ID = "4200000000202609251234567900"
OUT_REFUND_NO = "R-refund-notify-query-race-r42-001"
REFUND_ID = "refund-notify-query-race-r42-001"
EVENT_ID = "EV-refund-notify-query-race-r42-001"
NOTIFY_KEY = f"wechat_pay_notify:{EVENT_ID}"
QUERY_KEY = f"wechat_pay_notify:query:refund:{OUT_REFUND_NO}"


class _MockWechatPay:
    """为通知与查询入口提供不触网的本地支付集成。"""

    def is_ready(self) -> bool:
        return False


def _build_runtime_service(handle: DatabaseHandle) -> OrderPaymentRuntimeService:
    """构建真实退款通知与查询恢复入口。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=_MockWechatPay(),
        event_repo=OrderEventRepo(handle),
    )


def _refund_transaction() -> dict:
    """构造通知入口使用的已解密退款成功事务。"""
    return {
        "mchid": "mch-r42",
        "out_trade_no": ORDER_ID,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": OUT_REFUND_NO,
        "refund_id": REFUND_ID,
        "refund_status": "SUCCESS",
        "success_time": "2026-09-25T13:00:00+08:00",
        "amount": {
            "total": EXTERNAL_FEN,
            "refund": EXTERNAL_FEN,
            "payer_total": EXTERNAL_FEN,
            "payer_refund": EXTERNAL_FEN,
        },
    }


def _refund_query() -> dict:
    """构造查询恢复入口使用的退款成功结果。"""
    return {
        "mchid": "mch-r42",
        "out_trade_no": ORDER_ID,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": OUT_REFUND_NO,
        "refund_id": REFUND_ID,
        "refund_status": "SUCCESS",
        "success_time": "2026-09-25T13:00:00+08:00",
        "amount": {
            "total": EXTERNAL_FEN,
            "refund": EXTERNAL_FEN,
        },
    }


def _notify_body() -> bytes:
    """构造退款通知外层载荷。"""
    return json.dumps(
        {
            "id": EVENT_ID,
            "event_type": "REFUND.SUCCESS",
            "resource": {"kind": "refund"},
        },
        ensure_ascii=False,
    ).encode("utf-8")


async def _seed_paid_order(connection: aiosqlite.Connection) -> None:
    """写入已支付、含余额腿且外部微信腿可退款的真实订单。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '退款通知查询竞态会员', 'high', 1)",
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
            products="[]",
            total_amount=ORDER_AMOUNT_FEN / 100,
            delivery="{}",
            payment=json.dumps(
                {
                    "status": "paid",
                    "method": "combined",
                    "paidAt": "2026-09-25 12:00:00",
                    "transactionId": TRANSACTION_ID,
                    "externalPaidFen": EXTERNAL_FEN,
                    "couponFen": 0,
                    "balanceFen": BALANCE_FEN,
                    "pointsFen": 0,
                    "pointsUsed": 0,
                },
                ensure_ascii=False,
            ),
            status=OrderStatus.CONFIRMED,
            remark="",
            created_at="2026-09-25 11:00:00",
            updated_at="2026-09-25 12:00:00",
        )
    )
    await connection.commit()


async def _attempt_notify(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, dict | str]:
    """执行通知入口并区分业务冲突与瞬时锁冲突。"""
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


async def _attempt_query(
    service: OrderPaymentRuntimeService,
) -> tuple[str, dict | str]:
    """执行查询恢复入口并区分业务冲突与瞬时锁冲突。"""
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


@pytest.mark.asyncio
async def test_refund_notify_and_query_race_preserves_single_compensation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """通知与查询同时到达时只能产生一笔退款事实和一次余额补偿。"""
    database_path = tmp_path / "refund-notify-query-race-r42.db"
    notify_connection = await init_db(str(database_path))
    query_connection = await init_db(str(database_path))
    notify_handle = DatabaseHandle(notify_connection)
    query_handle = DatabaseHandle(query_connection)
    try:
        await _seed_paid_order(notify_connection)
        notify_service = _build_runtime_service(notify_handle)
        query_service = _build_runtime_service(query_handle)
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-r42")
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_verify_wechat_notify_signature",
            lambda self, raw_body, headers: True,
        )
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_decrypt_wechat_resource",
            lambda self, resource: _refund_transaction(),
        )
        raw_body = _notify_body()

        both_snapshots_read = asyncio.Event()
        observed_handles: set[int] = set()
        notify_handle_key = id(notify_handle)
        query_handle_key = id(query_handle)
        original_get_order = OrderRepo.get_order

        async def read_old_snapshot_together(
            repo: OrderRepo,
            order_id: str,
        ):
            """让两条入口先读同一支付快照，再只允许指定入口提交。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if (
                order_id == ORDER_ID
                and handle_key in {notify_handle_key, query_handle_key}
                and handle_key not in observed_handles
            ):
                observed_handles.add(handle_key)
                if len(observed_handles) == 2:
                    both_snapshots_read.set()
                await asyncio.wait_for(both_snapshots_read.wait(), timeout=5)
            return order

        monkeypatch.setattr(OrderRepo, "get_order", read_old_snapshot_together)

        async def run_notify() -> tuple[str, dict | str]:
            return await _attempt_notify(notify_service, raw_body)

        async def run_query() -> tuple[str, dict | str]:
            return await _attempt_query(query_service)

        notify_result, query_result = await asyncio.gather(
            run_notify(),
            run_query(),
        )

        initial_inbox_rows = await query_connection.execute_fetchall(
            "SELECT message_key, status, attempt_count, last_error "
            "FROM inbox_events WHERE message_key IN (?, ?) "
            "ORDER BY message_key",
            (NOTIFY_KEY, QUERY_KEY),
        )
        initial_inbox = {str(row["message_key"]): row for row in initial_inbox_rows}
        assert observed_handles == {notify_handle_key, query_handle_key}
        assert {result[0] for result in (notify_result, query_result)} <= {
            "locked",
            "ok",
        }
        assert str(initial_inbox[NOTIFY_KEY]["status"]) in {"failed", "processed"}
        assert str(initial_inbox[QUERY_KEY]["status"]) in {"failed", "processed"}
        assert sorted(int(row["attempt_count"]) for row in initial_inbox.values()) == [
            1,
            1,
        ]

        failed_keys = [
            str(row["message_key"])
            for row in initial_inbox_rows
            if str(row["status"]) == "failed"
        ]
        if failed_keys:
            for failed_key in failed_keys:
                await query_connection.execute(
                    "UPDATE inbox_events SET next_attempt_at = "
                    "datetime('now', '-1 second') WHERE message_key = ?",
                    (failed_key,),
                )
                await query_connection.commit()
                if failed_key == NOTIFY_KEY:
                    retry_result = await _attempt_notify(notify_service, raw_body)
                else:
                    retry_result = await _attempt_query(query_service)
                assert retry_result[0] == "ok"
                if len(failed_keys) == 1:
                    assert retry_result[1].get("duplicate") is True

        duplicate_notify = await _attempt_notify(notify_service, raw_body)
        await notify_handle.commit()
        duplicate_query = await _attempt_query(query_service)
        await query_handle.commit()
        assert duplicate_notify == ("ok", {"duplicate": True, "kind": "duplicate"})
        assert duplicate_query == ("ok", {"duplicate": True, "kind": "duplicate"})

        order_rows = await notify_connection.execute_fetchall(
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        )
        refund_rows = await notify_connection.execute_fetchall(
            "SELECT out_refund_no, transaction_id, payer_refund_fen "
            "FROM wechat_refund_events WHERE order_id = ?",
            (ORDER_ID,),
        )
        balance_rows = await notify_connection.execute_fetchall(
            "SELECT stored_value_fen, points FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        )
        ledger_rows = await notify_connection.execute_fetchall(
            "SELECT unique_id, amount_fen FROM balance_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        )
        inbox_rows = await notify_connection.execute_fetchall(
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key IN (?, ?) ORDER BY message_key",
            (NOTIFY_KEY, QUERY_KEY),
        )

        assert len(order_rows) == 1
        payment = json.loads(str(order_rows[0]["payment"]))
        assert str(order_rows[0]["status"]) == OrderStatus.CONFIRMED.value
        assert str(payment["status"]) == "paid"
        assert str(payment["refundStatus"]) == "full"
        assert int(payment["refundFen"]) == EXTERNAL_FEN
        assert [dict(row) for row in refund_rows] == [
            {
                "out_refund_no": OUT_REFUND_NO,
                "transaction_id": TRANSACTION_ID,
                "payer_refund_fen": EXTERNAL_FEN,
            }
        ]
        assert [dict(row) for row in balance_rows] == [
            {"stored_value_fen": INITIAL_BALANCE_FEN + BALANCE_FEN, "points": 0}
        ]
        assert [dict(row) for row in ledger_rows] == [
            {
                "unique_id": f"order_refund:{ORDER_ID}",
                "amount_fen": BALANCE_FEN,
            }
        ]
        assert {str(row["message_key"]): str(row["status"]) for row in inbox_rows} == {
            NOTIFY_KEY: "processed",
            QUERY_KEY: "processed",
        }
    finally:
        await close_db(query_connection)
        await close_db(notify_connection)
