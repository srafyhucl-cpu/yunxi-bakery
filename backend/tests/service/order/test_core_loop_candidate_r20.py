"""MiniApp 核心闭环 r20：订单关单与余额支付并发资产一致性。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.database import close_db, init_db
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.base import DatabaseHandle
from app.service.order.cancellation import OrderCancellationService
from app.service.order.expiration import OrderExpirationService
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.order.serialization import OrderSerializationService
from app.service.order.timeline import OrderTimelineService
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
    StoredValueService,
)
from tests.helpers.legacy_order_catalog import (
    LegacyOrderInventoryRepo,
    LegacyOrderProductRepo,
)

MOBILE = "13800001920"
OPENID = "openid_order_close_pay_race_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_close_pay_race_001"
INITIAL_BALANCE_FEN = 10_000
ORDER_AMOUNT_FEN = 5_000


def _build_member_service(handle: DatabaseHandle) -> MemberBalanceService:
    """为单个数据库连接构建会员余额服务。"""
    return MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )


def _build_payment_service(handle: DatabaseHandle) -> StoredValueOrderPaymentService:
    """为单个数据库连接构建订单余额支付服务。"""
    return StoredValueOrderPaymentService(
        order_repo=OrderRepo(handle),
        member_service=_build_member_service(handle),
    )


def _build_close_service(
    handle: DatabaseHandle,
    *,
    action: str,
) -> OrderCancellationService | OrderExpirationService:
    """按候选动作构建真实订单关单服务。"""
    order_repo = OrderRepo(handle)
    stored_value_service = StoredValueService(
        member_service=_build_member_service(handle),
        payment_service=_build_payment_service(handle),
    )
    timeline_service = OrderTimelineService(
        serialization_service=OrderSerializationService(),
        event_repo=OrderEventRepo(handle),
    )
    inventory_service = OrderInventoryService(
        product_repo=LegacyOrderProductRepo(handle),
        inventory_repo=LegacyOrderInventoryRepo(handle),
    )
    if action == "cancel":
        return OrderCancellationService(
            order_repo=order_repo,
            inventory_service=inventory_service,
            timeline_service=timeline_service,
            stored_value_service=stored_value_service,
        )
    return OrderExpirationService(
        order_repo=order_repo,
        inventory_service=inventory_service,
        timeline_service=timeline_service,
        stored_value_service=stored_value_service,
    )


async def _seed_order_and_member(connection: aiosqlite.Connection) -> None:
    """写入待支付订单、会员身份和足额余额。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '关单支付竞态会员', 'high', 1)",
        (f"cm_{OPENID}", MOBILE),
    )
    await connection.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (f"cil_{OPENID}", f"cm_{OPENID}", OPENID, OPENID),
    )
    await connection.execute(
        "INSERT INTO member_balance (mobile, stored_value_fen) VALUES (?, ?)",
        (MOBILE, INITIAL_BALANCE_FEN),
    )
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id) VALUES (?, 'miniapp', ?)",
        (f"session_{ORDER_ID}", USER_ID),
    )
    await connection.execute(
        "INSERT INTO orders (id, session_id, channel, user_id, products, "
        "total_amount, delivery, payment, status, created_at, updated_at) "
        "VALUES (?, ?, 'miniapp', ?, ?, ?, '{}', ?, 'pending', ?, ?)",
        (
            ORDER_ID,
            f"session_{ORDER_ID}",
            USER_ID,
            json.dumps(
                [
                    {
                        "product_id": "p_m2_001",
                        "title": "关单支付竞态蛋糕",
                        "price_fen": ORDER_AMOUNT_FEN,
                        "quantity": 1,
                        "inventory_reserved": False,
                    }
                ],
                ensure_ascii=False,
            ),
            ORDER_AMOUNT_FEN / 100,
            json.dumps(build_initial_payment(now_text()), ensure_ascii=False),
            now_text(),
            now_text(),
        ),
    )
    await connection.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("close_action", ["cancel", "expire"])
@pytest.mark.parametrize("winner", ["close", "payment"])
async def test_order_close_and_balance_payment_race_preserves_assets(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    close_action: str,
    winner: str,
) -> None:
    """关单与余额支付并发后，订单状态和余额流水必须保持原子一致。"""
    database_path = tmp_path / f"order-close-pay-race-{close_action}.db"
    close_connection = await init_db(str(database_path))
    pay_connection = await init_db(str(database_path))
    close_handle = DatabaseHandle(close_connection)
    pay_handle = DatabaseHandle(pay_connection)
    try:
        await _seed_order_and_member(close_connection)
        close_service = _build_close_service(close_handle, action=close_action)
        pay_service = _build_payment_service(pay_handle)

        initial_read_barrier = asyncio.Barrier(2)
        close_committed = asyncio.Event()
        payment_committed = asyncio.Event()
        winner_committed = close_committed if winner == "close" else payment_committed
        close_handle_key = id(close_handle)
        first_read_handles: set[int] = set()
        original_get_order = OrderRepo.get_order

        async def synchronized_initial_order_read(
            repo: OrderRepo,
            order_id: str,
        ):
            """只同步两个服务第一次读取待支付订单的时序。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if handle_key not in first_read_handles:
                first_read_handles.add(handle_key)
                await asyncio.wait_for(initial_read_barrier.wait(), timeout=5)
                role = "close" if handle_key == close_handle_key else "payment"
                if role != winner:
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(OrderRepo, "get_order", synchronized_initial_order_read)

        async def attempt_close() -> tuple[str, str]:
            """在一个独立请求事务中执行真实关单入口。"""
            try:
                async with close_service._order_repo.transaction():
                    if close_action == "cancel":
                        result = await close_service.cancel_user_order(
                            ORDER_ID,
                            user_id=USER_ID,
                        )
                    else:
                        result = await close_service.expire_unpaid_order(ORDER_ID)
                    serialized_status = str(result["status"])
                close_committed.set()
                return "ok", serialized_status
            except ValueError as exc:
                return "conflict", str(exc)
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                return "locked", str(exc)

        async def attempt_payment() -> tuple[str, str]:
            """在余额支付自己的生产事务中执行扣款。"""
            try:
                result = await pay_service.pay_order_with_balance(
                    ORDER_ID,
                    user_id=USER_ID,
                )
                payment_status = str(result["paymentStatus"])
                payment_committed.set()
                return "ok", payment_status
            except ValueError as exc:
                return "conflict", str(exc)
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                return "locked", str(exc)

        close_result, payment_result = await asyncio.gather(
            attempt_close(),
            attempt_payment(),
        )

        order_rows = await close_connection.execute_fetchall(
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        )
        balance_rows = await close_connection.execute_fetchall(
            "SELECT stored_value_fen FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        )
        balance_ledger_rows = await close_connection.execute_fetchall(
            "SELECT unique_id, amount_fen, balance_after_fen "
            "FROM balance_ledger WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        )
        event_rows = await close_connection.execute_fetchall(
            "SELECT status FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        )

        assert len(order_rows) == 1
        assert len(balance_rows) == 1
        final_order_status = str(order_rows[0]["status"])
        final_payment = json.loads(str(order_rows[0]["payment"]))
        final_payment_status = str(final_payment.get("status", ""))
        if final_payment_status == "paid":
            assert final_order_status == "pending"
            if close_result[0] == "ok":
                assert close_result == ("ok", "pending")
            else:
                assert close_result[0] in {"conflict", "locked"}
            assert payment_result == ("ok", "paid")
            assert int(balance_rows[0]["stored_value_fen"]) == (
                INITIAL_BALANCE_FEN - ORDER_AMOUNT_FEN
            )
            assert len(balance_ledger_rows) == 1
            assert str(balance_ledger_rows[0]["unique_id"]) == f"order_pay:{ORDER_ID}"
            assert int(balance_ledger_rows[0]["amount_fen"]) == -ORDER_AMOUNT_FEN
            assert int(balance_ledger_rows[0]["balance_after_fen"]) == (
                INITIAL_BALANCE_FEN - ORDER_AMOUNT_FEN
            )
            assert event_rows == []
        else:
            assert final_order_status == "cancelled"
            expected_payment_status = (
                "expired" if close_action == "expire" else "unpaid"
            )
            assert final_payment_status == expected_payment_status
            assert close_result == ("ok", "cancelled")
            assert payment_result[0] in {"conflict", "locked"}
            assert int(balance_rows[0]["stored_value_fen"]) == INITIAL_BALANCE_FEN
            assert balance_ledger_rows == []
            assert len(event_rows) == 1
            assert str(event_rows[0]["status"]) == "cancelled"
    finally:
        await close_db(pay_connection)
        await close_db(close_connection)
