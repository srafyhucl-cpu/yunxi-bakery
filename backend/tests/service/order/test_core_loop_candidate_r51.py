"""MiniApp 核心闭环 r51：用户取消与后台取消并发候选复核。"""

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
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order.cancellation import OrderCancellationService
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.order.serialization import OrderSerializationService
from app.service.order.status_flow import OrderAdminStatusService
from app.service.order.timeline import OrderTimelineService
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
    StoredValueService,
)
from tests.helpers.catalog_seed import seed_catalog_product

ITEM_ID = 81051
ORDER_ID = "order_user_admin_cancel_r51_001"
MOBILE = "13800003051"
OPENID = "user_admin_cancel_r51_001"
USER_ID = f"wx_{OPENID}"
ORDER_AMOUNT_FEN = 10_000
BALANCE_PAY_FEN = 2_000
INITIAL_BALANCE_FEN = 20_000


def _member_service(handle: DatabaseHandle) -> MemberBalanceService:
    """构建真实会员余额服务。"""
    return MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )


def _inventory_service(handle: DatabaseHandle) -> OrderInventoryService:
    """构建真实目录库存服务。"""
    return OrderInventoryService(
        product_repo=YouzanProductRepo(handle),
        inventory_repo=YouzanInventoryRepo(handle),
    )


def _stored_value_service(handle: DatabaseHandle) -> StoredValueService:
    """构建真实储值取消补偿服务。"""
    member_service = _member_service(handle)
    return StoredValueService(
        member_service=member_service,
        payment_service=StoredValueOrderPaymentService(
            order_repo=OrderRepo(handle),
            member_service=member_service,
        ),
    )


def _user_cancel_service(handle: DatabaseHandle) -> OrderCancellationService:
    """构建真实用户取消服务。"""
    return OrderCancellationService(
        order_repo=OrderRepo(handle),
        inventory_service=_inventory_service(handle),
        timeline_service=OrderTimelineService(
            serialization_service=OrderSerializationService(),
            event_repo=OrderEventRepo(handle),
        ),
        stored_value_service=_stored_value_service(handle),
    )


def _admin_cancel_service(handle: DatabaseHandle) -> OrderAdminStatusService:
    """构建真实后台取消服务。"""
    return OrderAdminStatusService(
        order_repo=OrderRepo(handle),
        inventory_service=_inventory_service(handle),
        timeline_service=OrderTimelineService(
            serialization_service=OrderSerializationService(),
            event_repo=OrderEventRepo(handle),
        ),
        stored_value_service=_stored_value_service(handle),
    )


async def _seed_partial_order(connection: aiosqlite.Connection) -> None:
    """写入会员、真实预占库存和已扣余额腿的组合支付订单。"""
    await seed_catalog_product(
        connection,
        item_id=ITEM_ID,
        title="用户后台并发取消蛋糕",
        price_fen=ORDER_AMOUNT_FEN,
        stock=1,
    )
    reserved = await YouzanInventoryRepo(connection).reserve_stock(str(ITEM_ID), 1)
    assert reserved is True
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '用户后台并发取消会员', 'high', 1)",
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
        "INSERT INTO member_balance (mobile, stored_value_fen, points) VALUES (?, ?, 0)",
        (MOBILE, INITIAL_BALANCE_FEN),
    )
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id, status) "
        "VALUES (?, 'miniapp', ?, 'active')",
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
                        "product_id": str(ITEM_ID),
                        "title": "用户后台并发取消蛋糕",
                        "price_fen": ORDER_AMOUNT_FEN,
                        "quantity": 1,
                        "uses_catalog_inventory": True,
                        "inventory_reserved": True,
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
    await connection.execute(
        "INSERT INTO order_events (order_id, status, operator, note, created_at) "
        "VALUES (?, 'pending', ?, '用户提交订单', ?)",
        (ORDER_ID, f"miniapp:{USER_ID}", now_text()),
    )
    await connection.commit()

    handle = DatabaseHandle(connection)
    member_service = _member_service(handle)
    service = StoredValueOrderPaymentService(
        order_repo=OrderRepo(handle),
        member_service=member_service,
    )
    result = await service.prepare_combined_payment(
        ORDER_ID,
        user_id=USER_ID,
        balance_fen=BALANCE_PAY_FEN,
    )
    assert result["payment"]["status"] == "partial"


async def _attempt_cancel(service, *, admin: bool) -> tuple[str, str]:
    """在独立生产事务中执行真实取消入口。"""
    try:
        async with service._order_repo.transaction():
            if admin:
                result = await service.update_admin_order_status(ORDER_ID, "cancelled")
            else:
                result = await service.cancel_user_order(ORDER_ID, user_id=USER_ID)
        return "ok", str(result["status"])
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["user", "admin"])
async def test_user_and_admin_cancel_race_release_assets_once(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    first_winner: str,
) -> None:
    """两个取消入口竞争后只能有一个状态胜者并执行一次资产补偿。"""
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
    database_path = tmp_path / f"user-admin-cancel-{first_winner}-r51.db"
    user_connection = await init_db(str(database_path))
    admin_connection = await init_db(str(database_path))
    user_handle = DatabaseHandle(user_connection)
    admin_handle = DatabaseHandle(admin_connection)
    try:
        await _seed_partial_order(user_connection)
        user_service = _user_cancel_service(user_handle)
        admin_service = _admin_cancel_service(admin_handle)

        first_read_barrier = asyncio.Barrier(2)
        winner_committed = asyncio.Event()
        first_read_handles: set[int] = set()
        user_handle_key = id(user_handle)
        original_get_order = OrderRepo.get_order

        async def synchronized_initial_order_read(
            repo: OrderRepo,
            order_id: str,
        ):
            """让两个取消入口读取同一旧快照并固定首胜顺序。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if order_id == ORDER_ID and handle_key not in first_read_handles:
                first_read_handles.add(handle_key)
                await asyncio.wait_for(first_read_barrier.wait(), timeout=5)
                role = "user" if handle_key == user_handle_key else "admin"
                if role != first_winner:
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(
            OrderRepo,
            "get_order",
            synchronized_initial_order_read,
        )

        async def run_user_cancel() -> tuple[str, str]:
            result = await _attempt_cancel(user_service, admin=False)
            if first_winner == "user":
                winner_committed.set()
            return result

        async def run_admin_cancel() -> tuple[str, str]:
            result = await _attempt_cancel(admin_service, admin=True)
            if first_winner == "admin":
                winner_committed.set()
            return result

        user_result, admin_result = await asyncio.gather(
            run_user_cancel(),
            run_admin_cancel(),
        )
        winner_result = user_result if first_winner == "user" else admin_result
        loser_result = admin_result if first_winner == "user" else user_result
        assert winner_result == ("ok", "cancelled")
        assert loser_result[0] in {"ok", "locked"}
        if loser_result[0] == "locked":
            retry_service = admin_service if first_winner == "user" else user_service
            retry_result = await _attempt_cancel(
                retry_service,
                admin=first_winner == "user",
            )
            assert retry_result == ("ok", "cancelled")

        order_rows = await user_connection.execute_fetchall(
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        )
        product_rows = await user_connection.execute_fetchall(
            "SELECT stock FROM youzan_products WHERE item_id = ?",
            (ITEM_ID,),
        )
        member_rows = await user_connection.execute_fetchall(
            "SELECT stored_value_fen FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        )
        ledger_rows = await user_connection.execute_fetchall(
            "SELECT unique_id, amount_fen, balance_after_fen "
            "FROM balance_ledger WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        )
        event_rows = await user_connection.execute_fetchall(
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        )

        assert len(order_rows) == 1
        assert str(order_rows[0]["status"]) == "cancelled"
        payment = json.loads(str(order_rows[0]["payment"]))
        assert payment["status"] == "partial"
        assert int(payment["balanceFen"]) == BALANCE_PAY_FEN
        assert [dict(row) for row in product_rows] == [{"stock": 1}]
        assert [dict(row) for row in member_rows] == [
            {"stored_value_fen": INITIAL_BALANCE_FEN}
        ]
        assert [dict(row) for row in ledger_rows] == [
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
        assert [dict(row) for row in event_rows] == [
            {
                "status": "pending",
                "operator": f"miniapp:{USER_ID}",
            },
            {
                "status": "cancelled",
                "operator": (
                    f"miniapp:{USER_ID}" if first_winner == "user" else "admin"
                ),
            },
        ]
    finally:
        await close_db(admin_connection)
        await close_db(user_connection)
