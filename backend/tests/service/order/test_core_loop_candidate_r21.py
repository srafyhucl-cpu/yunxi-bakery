"""MiniApp 核心闭环 r21：重复余额支付并发最多扣款一次。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.database import close_db, init_db
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_repo import OrderRepo
from app.repository.base import DatabaseHandle
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
)

MOBILE = "13800001921"
OPENID = "openid_duplicate_balance_pay_race_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_duplicate_balance_pay_race_001"
INITIAL_BALANCE_FEN = 10_000
ORDER_AMOUNT_FEN = 5_000


def _build_payment_service(handle: DatabaseHandle) -> StoredValueOrderPaymentService:
    """为单个数据库连接构建真实余额支付服务。"""
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )
    return StoredValueOrderPaymentService(
        order_repo=OrderRepo(handle),
        member_service=member_service,
    )


async def _seed_order_and_member(connection: aiosqlite.Connection) -> None:
    """写入待支付订单、会员身份和足额余额。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '重复余额支付竞态会员', 'high', 1)",
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
                        "title": "重复余额支付竞态蛋糕",
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
async def test_duplicate_balance_payment_race_deducts_once(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一订单并发余额支付最多只能产生一笔扣款流水。"""
    database_path = tmp_path / "duplicate-balance-payment-race.db"
    connection_a = await init_db(str(database_path))
    connection_b = await init_db(str(database_path))
    handle_a = DatabaseHandle(connection_a)
    handle_b = DatabaseHandle(connection_b)
    try:
        await _seed_order_and_member(connection_a)
        service_a = _build_payment_service(handle_a)
        service_b = _build_payment_service(handle_b)

        initial_read_barrier = asyncio.Barrier(2)
        first_read_handles: set[int] = set()
        original_get_order = OrderRepo.get_order

        async def synchronized_initial_order_read(
            repo: OrderRepo,
            order_id: str,
        ):
            """只同步两个支付服务第一次读取待支付订单的时序。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if handle_key not in first_read_handles:
                first_read_handles.add(handle_key)
                await initial_read_barrier.wait()
            return order

        monkeypatch.setattr(OrderRepo, "get_order", synchronized_initial_order_read)

        async def attempt(
            service: StoredValueOrderPaymentService,
        ) -> tuple[str, str]:
            """模拟一个独立 HTTP 请求的余额支付。"""
            try:
                result = await service.pay_order_with_balance(
                    ORDER_ID,
                    user_id=USER_ID,
                )
                return "ok", str(result["paymentStatus"])
            except ValueError as exc:
                return "conflict", str(exc)
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                return "locked", str(exc)

        results = await asyncio.gather(attempt(service_a), attempt(service_b))

        order_rows = await connection_a.execute_fetchall(
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        )
        balance_rows = await connection_a.execute_fetchall(
            "SELECT stored_value_fen FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        )
        ledger_rows = await connection_a.execute_fetchall(
            "SELECT unique_id, amount_fen, balance_after_fen "
            "FROM balance_ledger WHERE unique_id = ?",
            (f"order_pay:{ORDER_ID}",),
        )

        assert len(order_rows) == 1
        assert len(balance_rows) == 1
        final_payment = json.loads(str(order_rows[0]["payment"]))
        assert str(order_rows[0]["status"]) == "pending"
        assert str(final_payment.get("status")) == "paid"
        assert str(final_payment.get("method")) == "balance"
        assert int(final_payment.get("balanceFen", 0)) == ORDER_AMOUNT_FEN
        assert int(balance_rows[0]["stored_value_fen"]) == (
            INITIAL_BALANCE_FEN - ORDER_AMOUNT_FEN
        )
        assert len(ledger_rows) == 1
        assert int(ledger_rows[0]["amount_fen"]) == -ORDER_AMOUNT_FEN
        assert int(ledger_rows[0]["balance_after_fen"]) == (
            INITIAL_BALANCE_FEN - ORDER_AMOUNT_FEN
        )
        assert any(outcome == "ok" for outcome, _ in results)
        assert all(
            outcome != "ok" or payment_status == "paid"
            for outcome, payment_status in results
        )
    finally:
        await close_db(connection_b)
        await close_db(connection_a)
