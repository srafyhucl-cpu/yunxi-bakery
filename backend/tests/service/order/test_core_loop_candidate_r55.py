"""MiniApp 核心闭环 r55：用户取消与超时关闭并发候选复核。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.database import close_db, init_db
from app.repository.base import DatabaseHandle
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.order.expiration import OrderExpirationService
from app.service.order.serialization import OrderSerializationService
from app.service.order.timeline import OrderTimelineService
from tests.service.order.test_core_loop_candidate_r51 import (
    BALANCE_PAY_FEN,
    ITEM_ID,
    INITIAL_BALANCE_FEN,
    ORDER_AMOUNT_FEN,
    ORDER_ID,
    USER_ID,
    _inventory_service,
    _seed_partial_order,
    _stored_value_service,
    _user_cancel_service,
)


def _expiration_service(handle: DatabaseHandle) -> OrderExpirationService:
    """构建真实超时关闭服务，复用生产库存与储值补偿依赖。"""
    return OrderExpirationService(
        order_repo=OrderRepo(handle),
        inventory_service=_inventory_service(handle),
        timeline_service=OrderTimelineService(
            serialization_service=OrderSerializationService(),
            event_repo=OrderEventRepo(handle),
        ),
        stored_value_service=_stored_value_service(handle),
    )


async def _attempt_close(
    service,
    *,
    action: str,
) -> tuple[str, str]:
    """在独立生产事务中执行用户取消或超时关闭。"""
    try:
        async with service._order_repo.transaction():
            if action == "user":
                result = await service.cancel_user_order(ORDER_ID, user_id=USER_ID)
            else:
                result = await service.expire_unpaid_order(ORDER_ID)
            status = str(result["status"])
        return "ok", status
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _read_state(connection: aiosqlite.Connection) -> dict[str, list[dict]]:
    """读取订单、库存、余额、流水和关单事件最终事实。"""
    queries = {
        "order": (
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        ),
        "product": (
            "SELECT stock FROM youzan_products WHERE item_id = ?",
            (str(ITEM_ID),),
        ),
        "member": (
            "SELECT stored_value_fen FROM member_balance WHERE mobile = "
            "(SELECT primary_phone FROM customer_master WHERE id = ?)",
            (f"cm_{ORDER_ID}",),
        ),
        "balance_ledger": (
            "SELECT unique_id, amount_fen, balance_after_fen FROM balance_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "events": (
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
    }
    return {
        name: await connection.execute_fetchall(sql, parameters)
        for name, (sql, parameters) in queries.items()
    }


def _assert_state(state: dict[str, list[dict]], *, first_winner: str) -> None:
    """断言两个关单入口只产生一次库存、余额和事件副作用。"""
    assert len(state["order"]) == 1
    order = state["order"][0]
    payment = json.loads(str(order["payment"]))
    assert str(order["status"]) == "cancelled"
    assert str(payment["status"]) == (
        "partial" if first_winner == "user" else "expired"
    )
    assert int(payment["balanceFen"]) == BALANCE_PAY_FEN
    assert int(payment["remainFen"]) == ORDER_AMOUNT_FEN - BALANCE_PAY_FEN
    assert int(payment["externalPaidFen"]) == ORDER_AMOUNT_FEN - BALANCE_PAY_FEN
    assert [dict(row) for row in state["product"]] == [{"stock": 1}]
    assert [dict(row) for row in state["member"]] == [
        {"stored_value_fen": INITIAL_BALANCE_FEN}
    ]
    assert [dict(row) for row in state["balance_ledger"]] == [
        {
            "unique_id": f"combined_pay:{ORDER_ID}",
            "amount_fen": -BALANCE_PAY_FEN,
            "balance_after_fen": INITIAL_BALANCE_FEN - BALANCE_PAY_FEN,
        },
        {
            "unique_id": f"order_refund:{ORDER_ID}",
            "amount_fen": BALANCE_PAY_FEN,
            "balance_after_fen": INITIAL_BALANCE_FEN,
        },
    ]
    assert [dict(row) for row in state["events"]] == [
        {
            "status": "pending",
            "operator": f"miniapp:{USER_ID}",
        },
        {
            "status": "cancelled",
            "operator": (f"miniapp:{USER_ID}" if first_winner == "user" else "admin"),
        },
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["user", "expire"])
async def test_user_cancel_and_timeout_close_race_release_assets_once(
    tmp_path,
    first_winner: str,
) -> None:
    """用户取消与超时关闭竞争后只能有一个状态胜者和一次资产补偿。"""
    database_path = tmp_path / f"user-expire-close-{first_winner}-r55.db"
    user_connection = await init_db(str(database_path))
    expire_connection = await init_db(str(database_path))
    user_handle = DatabaseHandle(user_connection)
    expire_handle = DatabaseHandle(expire_connection)
    try:
        await _seed_partial_order(user_connection)
        user_service = _user_cancel_service(user_handle)
        expire_service = _expiration_service(expire_handle)

        initial_read_barrier = asyncio.Barrier(2)
        winner_committed = asyncio.Event()
        first_read_handles: set[int] = set()
        user_handle_key = id(user_handle)
        original_get_order = OrderRepo.get_order

        async def synchronized_initial_order_read(
            repo: OrderRepo,
            order_id: str,
        ):
            """让两个真实入口先读到同一 partial 快照，再固定首胜顺序。"""
            order = await original_get_order(repo, order_id)
            if order_id != ORDER_ID:
                return order
            handle_key = id(repo._db)
            if handle_key in first_read_handles:
                return order
            first_read_handles.add(handle_key)
            await asyncio.wait_for(initial_read_barrier.wait(), timeout=5)
            role = "user" if handle_key == user_handle_key else "expire"
            if role != first_winner:
                await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        OrderRepo.get_order = synchronized_initial_order_read
        try:

            async def run_user() -> tuple[str, str]:
                result = await _attempt_close(user_service, action="user")
                if first_winner == "user":
                    winner_committed.set()
                return result

            async def run_expire() -> tuple[str, str]:
                result = await _attempt_close(expire_service, action="expire")
                if first_winner == "expire":
                    winner_committed.set()
                return result

            user_result, expire_result = await asyncio.gather(
                run_user(),
                run_expire(),
            )
            winner_result = user_result if first_winner == "user" else expire_result
            loser_result = expire_result if first_winner == "user" else user_result
            assert winner_result == ("ok", "cancelled")
            assert loser_result[0] in {"ok", "locked"}

            if loser_result[0] == "locked":
                retry_service = (
                    expire_service if first_winner == "user" else user_service
                )
                retry_action = "expire" if first_winner == "user" else "user"
                assert await _attempt_close(retry_service, action=retry_action) == (
                    "ok",
                    "cancelled",
                )

            state = await _read_state(user_connection)
            _assert_state(state, first_winner=first_winner)
        finally:
            OrderRepo.get_order = original_get_order
    finally:
        await close_db(expire_connection)
        await close_db(user_connection)
