"""MiniApp 核心闭环 r23：组合支付与订单关单并发资产一致性。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.base import DatabaseHandle
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
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

MOBILE = "13800001923"
OPENID = "openid_combined_close_race_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_combined_close_race_001"
INITIAL_BALANCE_FEN = 20_000
ORDER_AMOUNT_FEN = 8_000
BALANCE_PAY_FEN = 2_000
REMAIN_FEN = ORDER_AMOUNT_FEN - BALANCE_PAY_FEN


def _build_member_service(handle: DatabaseHandle) -> MemberBalanceService:
    """为单个数据库连接构建会员余额服务。"""
    return MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )


def _build_payment_service(handle: DatabaseHandle) -> StoredValueOrderPaymentService:
    """为单个数据库连接构建组合支付服务。"""
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
        "VALUES (?, 'yunxi', 'active', ?, 1, '组合关单竞态会员', 'high', 1)",
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
                        "title": "组合关单竞态蛋糕",
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


async def _attempt_close(
    service: OrderCancellationService | OrderExpirationService,
    *,
    action: str,
) -> tuple[str, str]:
    """在一个独立请求事务中执行真实关单入口。"""
    try:
        async with service._order_repo.transaction():
            if action == "cancel":
                result = await service.cancel_user_order(ORDER_ID, user_id=USER_ID)
            else:
                result = await service.expire_unpaid_order(ORDER_ID)
            serialized_status = str(result["status"])
        return "ok", serialized_status
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_combined_payment(
    service: StoredValueOrderPaymentService,
) -> tuple[str, str]:
    """在生产事务中准备组合支付并记录支付结果。"""
    try:
        result = await service.prepare_combined_payment(
            ORDER_ID,
            user_id=USER_ID,
            balance_fen=BALANCE_PAY_FEN,
        )
        payment = result["payment"]
        return "ok", str(payment["status"])
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _read_final_state(
    connection: aiosqlite.Connection,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    """读取订单、余额、余额流水和关单事件快照。"""
    order_rows = await connection.execute_fetchall(
        "SELECT status, payment FROM orders WHERE id = ?",
        (ORDER_ID,),
    )
    balance_rows = await connection.execute_fetchall(
        "SELECT stored_value_fen FROM member_balance WHERE mobile = ?",
        (MOBILE,),
    )
    ledger_rows = await connection.execute_fetchall(
        "SELECT unique_id, amount_fen, balance_after_fen "
        "FROM balance_ledger WHERE biz_id = ? ORDER BY id",
        (ORDER_ID,),
    )
    event_rows = await connection.execute_fetchall(
        "SELECT status FROM order_events WHERE order_id = ? ORDER BY id",
        (ORDER_ID,),
    )
    return order_rows, balance_rows, ledger_rows, event_rows


def _assert_single_cancel_event(
    event_rows: list[dict[str, object]],
) -> None:
    """取消或超时胜出后只能留下一个关单事件。"""
    assert len(event_rows) == 1
    assert str(event_rows[0]["status"]) == "cancelled"


def _assert_close_won(
    *,
    action: str,
    close_result: tuple[str, str],
    payment_result: tuple[str, str],
    payment: dict[str, object],
    balance_rows: list[dict[str, object]],
    ledger_rows: list[dict[str, object]],
    event_rows: list[dict[str, object]],
) -> None:
    """关单先提交时，迟到组合支付不得留下任何资产副作用。"""
    assert close_result == ("ok", "cancelled")
    assert payment_result[0] in {"conflict", "locked"}
    assert str(payment["status"]) == ("expired" if action == "expire" else "unpaid")
    assert int(balance_rows[0]["stored_value_fen"]) == INITIAL_BALANCE_FEN
    assert ledger_rows == []
    _assert_single_cancel_event(event_rows)


def _assert_payment_won(
    *,
    action: str,
    close_result: tuple[str, str],
    close_retry_result: tuple[str, str] | None,
    payment_result: tuple[str, str],
    payment: dict[str, object],
    balance_rows: list[dict[str, object]],
    ledger_rows: list[dict[str, object]],
    event_rows: list[dict[str, object]],
) -> None:
    """组合支付先提交时，关单重试后必须只退款一次余额腿。"""
    assert payment_result == ("ok", "partial")
    assert close_result[0] in {"ok", "locked"}
    if close_result[0] == "locked":
        assert close_retry_result == ("ok", "cancelled")
    else:
        assert close_result == ("ok", "cancelled")
        assert close_retry_result is None
    assert str(payment["status"]) == ("expired" if action == "expire" else "partial")
    assert int(payment["balanceFen"]) == BALANCE_PAY_FEN
    assert int(payment["remainFen"]) == REMAIN_FEN
    assert int(payment["externalPaidFen"]) == REMAIN_FEN
    assert int(balance_rows[0]["stored_value_fen"]) == INITIAL_BALANCE_FEN
    assert len(ledger_rows) == 2
    assert str(ledger_rows[0]["unique_id"]) == f"combined_pay:{ORDER_ID}"
    assert int(ledger_rows[0]["amount_fen"]) == -BALANCE_PAY_FEN
    assert int(ledger_rows[0]["balance_after_fen"]) == (
        INITIAL_BALANCE_FEN - BALANCE_PAY_FEN
    )
    assert str(ledger_rows[1]["unique_id"]) == f"order_refund:{ORDER_ID}"
    assert int(ledger_rows[1]["amount_fen"]) == BALANCE_PAY_FEN
    assert int(ledger_rows[1]["balance_after_fen"]) == INITIAL_BALANCE_FEN
    _assert_single_cancel_event(event_rows)


@pytest.mark.asyncio
@pytest.mark.parametrize("close_action", ["cancel", "expire"])
@pytest.mark.parametrize("winner", ["close", "payment"])
async def test_combined_payment_and_order_close_race_preserves_assets(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    close_action: str,
    winner: str,
) -> None:
    """组合支付与关单并发后只能无扣款关单或扣款后完整退款。"""
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
    database_path = tmp_path / f"combined-close-race-{close_action}-{winner}.db"
    close_connection = await init_db(str(database_path))
    payment_connection = await init_db(str(database_path))
    close_handle = DatabaseHandle(close_connection)
    payment_handle = DatabaseHandle(payment_connection)
    try:
        await _seed_order_and_member(close_connection)
        close_service = _build_close_service(close_handle, action=close_action)
        payment_service = _build_payment_service(payment_handle)

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

        async def run_close() -> tuple[str, str]:
            """执行关单请求并在提交后释放等待方。"""
            result = await _attempt_close(close_service, action=close_action)
            close_committed.set()
            return result

        async def run_payment() -> tuple[str, str]:
            """执行组合支付请求并在提交后释放等待方。"""
            result = await _attempt_combined_payment(payment_service)
            payment_committed.set()
            return result

        close_result, payment_result = await asyncio.gather(
            run_close(),
            run_payment(),
        )
        close_retry_result = None
        if winner == "payment" and close_result[0] == "locked":
            close_retry_result = await _attempt_close(
                close_service,
                action=close_action,
            )
        order_rows, balance_rows, ledger_rows, event_rows = await _read_final_state(
            close_connection
        )

        assert len(order_rows) == 1
        assert len(balance_rows) == 1
        assert str(order_rows[0]["status"]) == "cancelled"
        payment = json.loads(str(order_rows[0]["payment"]))
        if winner == "close":
            _assert_close_won(
                action=close_action,
                close_result=close_result,
                payment_result=payment_result,
                payment=payment,
                balance_rows=balance_rows,
                ledger_rows=ledger_rows,
                event_rows=event_rows,
            )
        else:
            _assert_payment_won(
                action=close_action,
                close_result=close_result,
                close_retry_result=close_retry_result,
                payment_result=payment_result,
                payment=payment,
                balance_rows=balance_rows,
                ledger_rows=ledger_rows,
                event_rows=event_rows,
            )
    finally:
        await close_db(payment_connection)
        await close_db(close_connection)
