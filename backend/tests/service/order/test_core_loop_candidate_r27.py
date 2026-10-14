"""MiniApp 核心闭环 r27：超时关单与微信支付通知并发事实保留。"""

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
from app.service.order.expiration import OrderExpirationService
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.serialization import OrderSerializationService
from app.service.order.timeline import OrderTimelineService
from tests.helpers.legacy_order_catalog import (
    LegacyOrderInventoryRepo,
    LegacyOrderProductRepo,
)

ORDER_ID = "order_expire_payment_notify_race_001"
USER_ID = "wx_expire_payment_notify_race_001"
ORDER_AMOUNT_FEN = 19_800
TRANSACTION_ID = "4200000000202609250027001"
EVENT_ID = "EV-expire-payment-notify-race-001"


def _build_payment_service(handle: DatabaseHandle) -> OrderPaymentRuntimeService:
    """构建真实微信支付通知入账服务。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        event_repo=OrderEventRepo(handle),
    )


def _build_expiration_service(handle: DatabaseHandle) -> OrderExpirationService:
    """构建真实未支付超时关单服务。"""
    inventory_service = OrderInventoryService(
        product_repo=LegacyOrderProductRepo(handle),
        inventory_repo=LegacyOrderInventoryRepo(handle),
    )
    return OrderExpirationService(
        order_repo=OrderRepo(handle),
        inventory_service=inventory_service,
        timeline_service=OrderTimelineService(
            serialization_service=OrderSerializationService(),
            event_repo=OrderEventRepo(handle),
        ),
    )


async def _seed_order(connection: aiosqlite.Connection) -> None:
    """写入一个待支付、未预占库存的合成订单。"""
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id) VALUES (?, 'miniapp', ?)",
        (f"session_{ORDER_ID}", USER_ID),
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
                        "product_id": "p_expire_payment_race",
                        "title": "超时支付竞态蛋糕",
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
                    "createdAt": "2026-09-25 10:00:00",
                },
                ensure_ascii=False,
            ),
            "2026-09-25 10:00:00",
            "2026-09-25 10:00:00",
        ),
    )
    await connection.commit()


async def _attempt_payment_notify(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, str]:
    """通过公共通知入口执行真实支付入账。"""
    try:
        result = await service.handle_wechat_payment_notify(
            raw_body=raw_body,
            headers={},
        )
        return "ok", str(result["paymentStatus"])
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_expire(
    service: OrderExpirationService,
) -> tuple[str, str]:
    """在一个独立请求事务中执行真实超时关单。"""
    try:
        async with service._order_repo.transaction():
            result = await service.expire_unpaid_order(ORDER_ID)
            status = str(result["status"])
        return "ok", status
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


@pytest.mark.asyncio
async def test_timeout_winner_keeps_late_wechat_payment_after_intake_retry(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超时关单先提交时，通知重试必须保留微信到账并建立待退款。"""
    database_path = tmp_path / "expire-payment-notify-race.db"
    expiration_connection = await init_db(str(database_path))
    payment_connection = await init_db(str(database_path))
    expiration_handle = DatabaseHandle(expiration_connection)
    payment_handle = DatabaseHandle(payment_connection)
    try:
        await _seed_order(expiration_connection)
        expiration_service = _build_expiration_service(expiration_handle)
        payment_service = _build_payment_service(payment_handle)
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-expire-race")
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-expire-race")
        transaction = {
            "out_trade_no": ORDER_ID,
            "trade_state": "SUCCESS",
            "mchid": "mch-expire-race",
            "appid": "appid-expire-race",
            "amount": {"total": ORDER_AMOUNT_FEN, "currency": "CNY"},
            "transaction_id": TRANSACTION_ID,
            "success_time": "2026-09-25T10:35:00+08:00",
        }
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_verify_wechat_notify_signature",
            lambda self, raw_body, headers: True,
        )
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_decrypt_wechat_resource",
            lambda self, resource: transaction,
        )
        raw_body = json.dumps(
            {"id": EVENT_ID, "event_type": "TRANSACTION.SUCCESS", "resource": {}},
            ensure_ascii=False,
        ).encode("utf-8")

        payment_snapshot_read = asyncio.Event()
        expiration_committed = asyncio.Event()
        payment_handle_key = id(payment_handle)
        payment_read_count = 0
        original_get_order = OrderRepo.get_order

        async def read_then_wait_for_expiration(
            repo: OrderRepo,
            order_id: str,
        ):
            """让支付入账先读到旧状态，再等待超时关单提交。"""
            nonlocal payment_read_count
            order = await original_get_order(repo, order_id)
            if id(repo._db) == payment_handle_key and order_id == ORDER_ID:
                payment_read_count += 1
                if payment_read_count == 3:
                    payment_snapshot_read.set()
                    await asyncio.wait_for(expiration_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(OrderRepo, "get_order", read_then_wait_for_expiration)

        async def run_payment() -> tuple[str, str]:
            """执行首次支付通知，由服务内部同步点确保先完成旧状态读取。"""
            return await _attempt_payment_notify(payment_service, raw_body)

        async def run_expiration() -> tuple[str, str]:
            """执行超时关单并在提交后唤醒支付通知。"""
            await asyncio.wait_for(payment_snapshot_read.wait(), timeout=5)
            result = await _attempt_expire(expiration_service)
            expiration_committed.set()
            return result

        first_payment_result, expiration_result = await asyncio.gather(
            run_payment(),
            run_expiration(),
        )

        inbox_rows = await payment_connection.execute_fetchall(
            "SELECT status, attempt_count, last_error FROM inbox_events "
            "WHERE message_key = ?",
            (f"wechat_pay_notify:{EVENT_ID}",),
        )
        assert first_payment_result[0] == "locked"
        assert expiration_result == ("ok", "cancelled")
        assert len(inbox_rows) == 1
        assert str(inbox_rows[0]["status"]) == "failed"
        assert int(inbox_rows[0]["attempt_count"]) == 1
        assert "locked" in str(inbox_rows[0]["last_error"]).lower()

        await payment_connection.execute(
            "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
            "WHERE message_key = ?",
            (f"wechat_pay_notify:{EVENT_ID}",),
        )
        await payment_connection.commit()
        retry_result = await _attempt_payment_notify(payment_service, raw_body)

        order_rows = await expiration_connection.execute_fetchall(
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        )
        event_rows = await expiration_connection.execute_fetchall(
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        )
        transaction_rows = await expiration_connection.execute_fetchall(
            "SELECT order_id FROM payment_transactions WHERE transaction_id = ?",
            (TRANSACTION_ID,),
        )
        final_inbox_rows = await payment_connection.execute_fetchall(
            "SELECT status, attempt_count FROM inbox_events WHERE message_key = ?",
            (f"wechat_pay_notify:{EVENT_ID}",),
        )
        payment = json.loads(str(order_rows[0]["payment"]))

        assert retry_result == ("ok", "paid")
        assert str(order_rows[0]["status"]) == "cancelled"
        assert str(payment["status"]) == "paid"
        assert str(payment["transactionId"]) == TRANSACTION_ID
        assert str(payment["refundStatus"]) == "pending"
        assert int(payment["refundAmountFen"]) == ORDER_AMOUNT_FEN
        assert str(payment["expiredReason"]) == "payment_timeout"
        assert [(row["status"], row["operator"]) for row in event_rows] == [
            ("cancelled", "admin"),
            ("paid", "wechat-pay"),
        ]
        assert [dict(row) for row in transaction_rows] == [{"order_id": ORDER_ID}]
        assert len(final_inbox_rows) == 1
        assert str(final_inbox_rows[0]["status"]) == "processed"
        assert int(final_inbox_rows[0]["attempt_count"]) == 2
    finally:
        await close_db(payment_connection)
        await close_db(expiration_connection)
