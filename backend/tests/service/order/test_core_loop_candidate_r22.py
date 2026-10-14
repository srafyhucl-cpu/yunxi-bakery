"""MiniApp 核心闭环 r22：组合支付并发份额最多入账一次。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.config import settings
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

MOBILE = "13800001922"
OPENID = "openid_combined_payment_race_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_combined_payment_race_001"
INITIAL_BALANCE_FEN = 20_000
ORDER_AMOUNT_FEN = 8_000


def _build_payment_service(handle: DatabaseHandle) -> StoredValueOrderPaymentService:
    """为单个数据库连接构建真实组合支付服务。"""
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
        "VALUES (?, 'yunxi', 'active', ?, 1, '组合支付竞态会员', 'high', 1)",
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
                        "title": "组合支付竞态蛋糕",
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
@pytest.mark.parametrize(
    "requested_balance_fens",
    [
        (2_000, 2_000),
        (2_000, 3_000),
    ],
    ids=["same-split", "different-splits"],
)
async def test_concurrent_combined_payment_race_deducts_once(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    requested_balance_fens: tuple[int, int],
) -> None:
    """同额或异额组合支付并发后只能保留一笔匹配快照的余额扣款。"""
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
    database_path = tmp_path / (
        f"combined-payment-race-{requested_balance_fens[0]}-{requested_balance_fens[1]}.db"
    )
    connection_a = await init_db(str(database_path))
    connection_b = await init_db(str(database_path))
    handle_a = DatabaseHandle(connection_a)
    handle_b = DatabaseHandle(connection_b)
    try:
        await _seed_order_and_member(connection_a)
        service_a = _build_payment_service(handle_a)
        service_b = _build_payment_service(handle_b)

        inner_read_barrier = asyncio.Barrier(2)
        read_counts: dict[int, int] = {}
        original_get_order = OrderRepo.get_order

        async def synchronized_inner_order_read(
            repo: OrderRepo,
            order_id: str,
        ):
            """只同步两个组合支付事务内的第二次订单读取。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            read_counts[handle_key] = read_counts.get(handle_key, 0) + 1
            if read_counts[handle_key] == 2:
                await inner_read_barrier.wait()
            return order

        monkeypatch.setattr(OrderRepo, "get_order", synchronized_inner_order_read)

        async def attempt(
            service: StoredValueOrderPaymentService,
            balance_fen: int,
        ) -> tuple[str, int | str]:
            """模拟一个独立 HTTP 请求的组合支付准备。"""
            try:
                result = await service.prepare_combined_payment(
                    ORDER_ID,
                    user_id=USER_ID,
                    balance_fen=balance_fen,
                )
                return "ok", int(result["payment"]["balanceFen"])
            except ValueError as exc:
                return "conflict", str(exc)
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                return "locked", str(exc)

        results = await asyncio.gather(
            attempt(service_a, requested_balance_fens[0]),
            attempt(service_b, requested_balance_fens[1]),
        )

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
            (f"combined_pay:{ORDER_ID}",),
        )

        assert len(order_rows) == 1
        assert len(balance_rows) == 1
        payment = json.loads(str(order_rows[0]["payment"]))
        final_balance_fen = int(payment["balanceFen"])
        final_remain_fen = int(payment["remainFen"])
        assert str(order_rows[0]["status"]) == "pending"
        assert str(payment["status"]) == "partial"
        assert str(payment["method"]) == "combined"
        assert final_balance_fen in requested_balance_fens
        assert final_remain_fen == ORDER_AMOUNT_FEN - final_balance_fen
        assert int(payment["externalPaidFen"]) == final_remain_fen
        assert int(balance_rows[0]["stored_value_fen"]) == (
            INITIAL_BALANCE_FEN - final_balance_fen
        )
        assert len(ledger_rows) == 1
        assert int(ledger_rows[0]["amount_fen"]) == -final_balance_fen
        assert int(ledger_rows[0]["balance_after_fen"]) == (
            INITIAL_BALANCE_FEN - final_balance_fen
        )
        successful_results = [value for outcome, value in results if outcome == "ok"]
        assert successful_results == [final_balance_fen]
    finally:
        await close_db(connection_b)
        await close_db(connection_a)
