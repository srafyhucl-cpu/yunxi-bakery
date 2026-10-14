"""MiniApp 核心闭环 r58：退款查询与后台确认并发候选复核。"""

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
from app.service.order import notify_intake
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.serialization import OrderSerializationService
from app.service.order.status_flow import OrderAdminStatusService
from app.service.order.timeline import OrderTimelineService
from tests.helpers.legacy_order_catalog import (
    LegacyOrderInventoryRepo,
    LegacyOrderProductRepo,
)

ORDER_ID = "order_refund_query_admin_confirm_r58_001"
USER_ID = "wx_refund_query_admin_confirm_r58_001"
ORDER_AMOUNT_FEN = 10_000
TRANSACTION_ID = "4200000000202609251234567958"
OUT_REFUND_NO = "R-refund-query-admin-confirm-r58-001"
REFUND_ID = "refund-refund-query-admin-confirm-r58-001"
MCH_ID = "mch-refund-query-admin-confirm-r58"
REFUND_KEY = f"wechat_pay_notify:query:refund:{OUT_REFUND_NO}"


class _LocalWechatPay:
    """为退款查询恢复提供不触网的本地支付集成。"""

    def is_ready(self) -> bool:
        return False

    def format_success_time(self, value: str) -> str:
        return "2026-09-25 18:00:00"


def _build_admin_service(handle: DatabaseHandle) -> OrderAdminStatusService:
    """构建真实后台订单状态服务。"""
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
    )


def _build_refund_query_service(handle: DatabaseHandle) -> OrderPaymentRuntimeService:
    """构建真实退款查询恢复服务。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=_LocalWechatPay(),
        event_repo=OrderEventRepo(handle),
    )


async def _seed_paid_pending_order(connection: aiosqlite.Connection) -> None:
    """写入已支付但尚未由后台确认的合成订单。"""
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id) VALUES (?, 'miniapp', ?)",
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
                    "method": "wechat",
                    "paidAt": "2026-09-25 17:00:00",
                    "transactionId": TRANSACTION_ID,
                    "externalPaidFen": ORDER_AMOUNT_FEN,
                    "couponFen": 0,
                    "balanceFen": 0,
                    "pointsFen": 0,
                    "pointsUsed": 0,
                },
                ensure_ascii=False,
            ),
            status=OrderStatus.PENDING,
            remark="",
            created_at="2026-09-25 16:00:00",
            updated_at="2026-09-25 17:00:00",
        )
    )
    await connection.commit()


def _refund_query() -> dict:
    """构造与支付快照完全匹配的全额退款查询。"""
    return {
        "mchid": MCH_ID,
        "out_trade_no": ORDER_ID,
        "out_refund_no": OUT_REFUND_NO,
        "refund_id": REFUND_ID,
        "refund_status": "SUCCESS",
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T18:05:00+08:00",
        "amount": {
            "total": ORDER_AMOUNT_FEN,
            "refund": ORDER_AMOUNT_FEN,
        },
    }


async def _attempt_admin_confirm(
    service: OrderAdminStatusService,
) -> tuple[str, str]:
    """在独立后台请求事务中执行真实确认。"""
    try:
        async with service._order_repo.transaction():
            result = await service.update_admin_order_status(ORDER_ID, "confirmed")
        return "ok", str(result["status"])
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_refund_query(
    service: OrderPaymentRuntimeService,
) -> tuple[str, dict | str]:
    """执行真实退款查询恢复入口。"""
    try:
        result = await service.reconcile_refund_from_query(
            _refund_query(),
            payer_total_fen=ORDER_AMOUNT_FEN,
        )
        return "ok", result
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _read_state(connection: aiosqlite.Connection) -> dict[str, list[dict]]:
    """读取订单、退款、交易、事件和 inbox 最终事实。"""
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
        "refunds": (
            "SELECT out_refund_no, transaction_id, payer_refund_fen, source "
            "FROM wechat_refund_events WHERE order_id = ?",
            (ORDER_ID,),
        ),
        "events": (
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "inbox": (
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key = ?",
            (REFUND_KEY,),
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
) -> None:
    """断言退款查询事实和后台确认只能形成合法终态。"""
    assert len(state["order"]) == 1
    order = state["order"][0]
    payment = json.loads(str(order["payment"]))
    assert str(order["status"]) == (
        "confirmed" if first_winner == "admin" else OrderStatus.PENDING.value
    )
    assert payment["status"] == "paid"
    assert payment["method"] == "wechat"
    assert payment["transactionId"] == TRANSACTION_ID
    assert payment["refundStatus"] == "full"
    assert int(payment["refundFen"]) == ORDER_AMOUNT_FEN
    assert [dict(row) for row in state["transactions"]] == [
        {"transaction_id": TRANSACTION_ID, "order_id": ORDER_ID}
    ]
    assert [dict(row) for row in state["refunds"]] == [
        {
            "out_refund_no": OUT_REFUND_NO,
            "transaction_id": TRANSACTION_ID,
            "payer_refund_fen": ORDER_AMOUNT_FEN,
            "source": "query",
        }
    ]
    assert [dict(row) for row in state["events"]] == (
        [{"status": "confirmed", "operator": "admin"}]
        if first_winner == "admin"
        else []
    )
    assert [dict(row) for row in state["inbox"]] == [
        {
            "message_key": REFUND_KEY,
            "status": "processed",
            "attempt_count": 1,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["refund", "admin"])
async def test_refund_query_and_admin_confirm_race_preserves_refund_guard(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    first_winner: str,
) -> None:
    """退款先到时，后台旧快照不得把已全额退款订单推进到已确认。"""
    database_path = tmp_path / f"refund-query-admin-confirm-{first_winner}-r58.db"
    admin_connection = await init_db(str(database_path))
    refund_connection = await init_db(str(database_path))
    admin_handle = DatabaseHandle(admin_connection)
    refund_handle = DatabaseHandle(refund_connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        await _seed_paid_pending_order(admin_connection)
        admin_service = _build_admin_service(admin_handle)
        refund_service = _build_refund_query_service(refund_handle)
        admin_committed = asyncio.Event()
        refund_committed = asyncio.Event()
        admin_old_snapshot_read = asyncio.Event()
        refund_claim_committed = asyncio.Event()
        admin_handle_key = id(admin_handle)
        refund_handle_key = id(refund_handle)
        original_get_order = OrderRepo.get_order
        original_claim_notify_key = notify_intake.claim_notify_key

        async def synchronize_order_read(repo: OrderRepo, order_id: str):
            """固定两个入口的旧快照读取与提交顺序。"""
            if order_id != ORDER_ID:
                return await original_get_order(repo, order_id)
            if id(repo._db) != admin_handle_key and first_winner == "admin":
                await asyncio.wait_for(admin_committed.wait(), timeout=5)
            order = await original_get_order(repo, order_id)
            if id(repo._db) == admin_handle_key and first_winner == "refund":
                admin_old_snapshot_read.set()
                await asyncio.wait_for(refund_committed.wait(), timeout=5)
            return order

        async def commit_refund_claim_before_business(
            db,
            message_key: str,
            payload: dict | None = None,
            *,
            lease_seconds: int = notify_intake.DEFAULT_NOTIFY_LEASE_SECONDS,
        ) -> dict:
            """先提交退款查询 claim，避免 claim 写锁改变业务首胜顺序。"""
            claim = await original_claim_notify_key(
                db,
                message_key,
                payload,
                lease_seconds=lease_seconds,
            )
            if id(db) == refund_handle_key:
                await db.commit()
                refund_claim_committed.set()
            return claim

        monkeypatch.setattr(OrderRepo, "get_order", synchronize_order_read)
        monkeypatch.setattr(
            notify_intake,
            "claim_notify_key",
            commit_refund_claim_before_business,
        )

        async def run_refund() -> tuple[str, dict | str]:
            result = await _attempt_refund_query(refund_service)
            refund_committed.set()
            return result

        async def run_admin() -> tuple[str, str]:
            result = await _attempt_admin_confirm(admin_service)
            admin_committed.set()
            return result

        if first_winner == "refund":
            admin_task = asyncio.create_task(run_admin())
            await asyncio.wait_for(admin_old_snapshot_read.wait(), timeout=5)
            refund_task = asyncio.create_task(run_refund())
            refund_result, admin_result = await asyncio.gather(
                refund_task,
                admin_task,
            )
        else:
            refund_task = asyncio.create_task(run_refund())
            await asyncio.wait_for(refund_claim_committed.wait(), timeout=5)
            admin_task = asyncio.create_task(run_admin())
            refund_result, admin_result = await asyncio.gather(
                refund_task,
                admin_task,
            )
        if first_winner == "refund" and admin_result[0] == "locked":
            admin_result = await _attempt_admin_confirm(admin_service)
        if first_winner == "refund":
            assert refund_result[0] == "ok"
            assert admin_result[0] == "conflict"
            assert admin_result[1] == "订单已退款，不能进入履约"
        else:
            assert refund_result[0] == "ok"
            assert admin_result == ("ok", OrderStatus.CONFIRMED.value)

        duplicate_result = await _attempt_refund_query(refund_service)
        await refund_handle.commit()
        assert duplicate_result[0] == "ok"
        assert duplicate_result[1] == {
            "duplicate": True,
            "kind": "duplicate",
        }
        _assert_state(
            await _read_state(refund_connection),
            first_winner=first_winner,
        )
    finally:
        await close_db(refund_connection)
        await close_db(admin_connection)
