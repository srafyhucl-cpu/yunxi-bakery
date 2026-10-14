"""MiniApp 核心闭环 r39：已应用券订单的后台取消与余额支付竞态。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.database import close_db, init_db
from app.models.coupon import CouponTemplate, CouponType
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.base import DatabaseHandle
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.coupon import CouponService
from app.service.coupon.inventory import CouponInventoryService
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.order.serialization import OrderSerializationService
from app.service.order.status_flow import OrderAdminStatusService
from app.service.order.timeline import OrderTimelineService
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
)
from tests.helpers.legacy_order_catalog import (
    LegacyOrderInventoryRepo,
    LegacyOrderProductRepo,
)

MOBILE = "13800003039"
OPENID = "admin_cancel_coupon_balance_r39_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_admin_cancel_coupon_balance_r39_001"
COUPON_ID = "coupon_admin_cancel_balance_r39_001"
COUPON_FEN = 500
ORDER_AMOUNT_FEN = 10_000
BALANCE_PAY_FEN = ORDER_AMOUNT_FEN - COUPON_FEN
INITIAL_BALANCE_FEN = 20_000


def _build_coupon_service(handle: DatabaseHandle) -> CouponService:
    """为单个数据库连接构建真实优惠券服务。"""
    return CouponService(
        template_repo=CouponTemplateRepo(handle),
        inventory_repo=CouponInventoryRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
        order_repo=OrderRepo(handle),
        inventory_service=CouponInventoryService(handle),
    )


def _build_member_service(handle: DatabaseHandle) -> MemberBalanceService:
    """为单个数据库连接构建真实会员余额服务。"""
    return MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )


def _build_payment_service(handle: DatabaseHandle) -> StoredValueOrderPaymentService:
    """为单个数据库连接构建真实余额支付服务。"""
    return StoredValueOrderPaymentService(
        order_repo=OrderRepo(handle),
        member_service=_build_member_service(handle),
    )


def _build_admin_service(handle: DatabaseHandle) -> OrderAdminStatusService:
    """为单个数据库连接构建真实后台订单状态服务。"""
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


async def _seed_coupon_order_and_member(connection: aiosqlite.Connection) -> None:
    """写入会员、余额、待支付订单和一张可用券。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '券余额后台取消竞态会员', 'high', 1)",
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
                        "product_id": "p_admin_cancel_coupon_balance_r39",
                        "title": "券余额后台取消竞态蛋糕",
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
    template_id = "cg_admin_cancel_coupon_balance_r39_001"
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=template_id,
            name="券余额后台取消竞态测试券",
            coupon_type=CouponType.FULL_REDUCTION,
            threshold_fen=3_000,
            value_fen=COUPON_FEN,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await CouponInventoryRepo(connection).insert(
        CouponInventoryEntry(
            coupon_id=COUPON_ID,
            status=CouponStatus.TAKE,
            mobile=MOBILE,
            coupon_group_id=template_id,
            title="券余额后台取消竞态测试券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id=template_id,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()


async def _apply_coupon_snapshot(connection: aiosqlite.Connection) -> None:
    """用真实优惠券服务预置 partial 券快照。"""
    service = _build_coupon_service(DatabaseHandle(connection))
    await service.apply_coupon(ORDER_ID, user_id=USER_ID, coupon_id=COUPON_ID)
    await connection.commit()


async def _attempt_admin_cancel(
    service: OrderAdminStatusService,
) -> tuple[str, str]:
    """在生产后台应用服务等价事务中执行取消。"""
    try:
        async with service._order_repo.transaction():
            result = await service.update_admin_order_status(ORDER_ID, "cancelled")
            status = str(result["status"])
        return "ok", status
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_balance_payment(
    service: StoredValueOrderPaymentService,
) -> tuple[str, str]:
    """在独立生产事务中执行全额余额支付剩余金额。"""
    try:
        result = await service.pay_order_with_balance(ORDER_ID, user_id=USER_ID)
        return "ok", str(result["paymentStatus"])
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
    list[dict[str, object]],
]:
    """读取订单、余额、余额流水、券生命周期和取消事件。"""
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
    coupon_rows = await connection.execute_fetchall(
        "SELECT coupon_id, status, order_no, deducted_fen "
        "FROM coupon_inventory WHERE coupon_id = ? ORDER BY id",
        (COUPON_ID,),
    )
    event_rows = await connection.execute_fetchall(
        "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
        (ORDER_ID,),
    )
    return order_rows, balance_rows, ledger_rows, coupon_rows, event_rows


def _assert_admin_cancel_won(
    order_rows: list[dict[str, object]],
    balance_rows: list[dict[str, object]],
    ledger_rows: list[dict[str, object]],
    coupon_rows: list[dict[str, object]],
    event_rows: list[dict[str, object]],
) -> None:
    """取消先提交时不得扣款、核销券或保留 partial 快照。"""
    assert len(order_rows) == 1
    assert str(order_rows[0]["status"]) == "cancelled"
    payment = json.loads(str(order_rows[0]["payment"]))
    assert str(payment["status"]) == "unpaid"
    assert str(payment.get("couponId", "")) == ""
    assert int(payment.get("couponFen", 0)) == 0
    assert int(payment.get("balanceFen", 0)) == 0
    assert int(balance_rows[0]["stored_value_fen"]) == INITIAL_BALANCE_FEN
    assert ledger_rows == []
    assert len(coupon_rows) == 1
    assert str(coupon_rows[0]["status"]) == CouponStatus.TAKE
    assert str(coupon_rows[0]["order_no"] or "") == ""
    assert len(event_rows) == 1
    assert str(event_rows[0]["status"]) == "cancelled"
    assert str(event_rows[0]["operator"]) == "admin"


def _assert_payment_won(
    order_rows: list[dict[str, object]],
    balance_rows: list[dict[str, object]],
    ledger_rows: list[dict[str, object]],
    coupon_rows: list[dict[str, object]],
    event_rows: list[dict[str, object]],
) -> None:
    """支付先提交时只扣剩余余额并核销券，后台取消不得留下事件。"""
    assert len(order_rows) == 1
    assert str(order_rows[0]["status"]) == "pending"
    payment = json.loads(str(order_rows[0]["payment"]))
    assert str(payment["status"]) == "paid"
    assert str(payment["couponId"]) == COUPON_ID
    assert int(payment["couponFen"]) == COUPON_FEN
    assert int(payment["balanceFen"]) == BALANCE_PAY_FEN
    assert int(balance_rows[0]["stored_value_fen"]) == (
        INITIAL_BALANCE_FEN - BALANCE_PAY_FEN
    )
    assert len(ledger_rows) == 1
    assert str(ledger_rows[0]["unique_id"]) == f"order_pay:{ORDER_ID}"
    assert int(ledger_rows[0]["amount_fen"]) == -BALANCE_PAY_FEN
    assert int(ledger_rows[0]["balance_after_fen"]) == (
        INITIAL_BALANCE_FEN - BALANCE_PAY_FEN
    )
    assert len(coupon_rows) == 2
    assert str(coupon_rows[-1]["status"]) == CouponStatus.CONSUME
    assert str(coupon_rows[-1]["order_no"]) == ORDER_ID
    assert int(coupon_rows[-1]["deducted_fen"]) == COUPON_FEN
    assert event_rows == []


@pytest.mark.asyncio
@pytest.mark.parametrize("winner", ["admin", "payment"])
async def test_admin_cancel_and_coupon_balance_payment_race_preserves_assets(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    winner: str,
) -> None:
    """三方竞态后只能无扣款取消或余额扣款并核销券一种完整事实。"""
    database_path = tmp_path / f"admin-cancel-coupon-balance-{winner}-r39.db"
    admin_connection = await init_db(str(database_path))
    payment_connection = await init_db(str(database_path))
    admin_handle = DatabaseHandle(admin_connection)
    payment_handle = DatabaseHandle(payment_connection)
    try:
        await _seed_coupon_order_and_member(admin_connection)
        await _apply_coupon_snapshot(admin_connection)
        admin_service = _build_admin_service(admin_handle)
        payment_service = _build_payment_service(payment_handle)

        initial_read_barrier = asyncio.Barrier(2)
        admin_committed = asyncio.Event()
        payment_committed = asyncio.Event()
        winner_committed = admin_committed if winner == "admin" else payment_committed
        admin_handle_key = id(admin_handle)
        first_read_handles: set[int] = set()
        original_get_order = OrderRepo.get_order

        async def synchronized_initial_order_read(
            repo: OrderRepo,
            order_id: str,
        ):
            """同步两个事务首次读取 partial 券快照并固定胜出顺序。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if handle_key not in first_read_handles:
                first_read_handles.add(handle_key)
                await asyncio.wait_for(initial_read_barrier.wait(), timeout=5)
                role = "admin" if handle_key == admin_handle_key else "payment"
                if role != winner:
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(OrderRepo, "get_order", synchronized_initial_order_read)

        async def run_admin() -> tuple[str, str]:
            result = await _attempt_admin_cancel(admin_service)
            admin_committed.set()
            return result

        async def run_payment() -> tuple[str, str]:
            result = await _attempt_balance_payment(payment_service)
            payment_committed.set()
            return result

        admin_result, payment_result = await asyncio.gather(
            run_admin(),
            run_payment(),
        )
        admin_retry_result = None
        if winner == "payment" and admin_result[0] == "locked":
            admin_retry_result = await _attempt_admin_cancel(admin_service)

        state = await _read_final_state(admin_connection)
        order_rows, balance_rows, ledger_rows, coupon_rows, event_rows = state
        if winner == "admin":
            assert admin_result == ("ok", "cancelled")
            assert payment_result[0] in {"conflict", "locked"}
            assert admin_retry_result is None
            _assert_admin_cancel_won(
                order_rows,
                balance_rows,
                ledger_rows,
                coupon_rows,
                event_rows,
            )
        else:
            assert payment_result == ("ok", "paid")
            assert admin_result[0] in {"ok", "locked", "conflict"}
            if admin_result[0] == "locked":
                assert admin_retry_result == (
                    "conflict",
                    "已支付订单不允许取消",
                )
            else:
                assert admin_result == (
                    "conflict",
                    "已支付订单不允许取消",
                )
                assert admin_retry_result is None
            _assert_payment_won(
                order_rows,
                balance_rows,
                ledger_rows,
                coupon_rows,
                event_rows,
            )
    finally:
        await close_db(payment_connection)
        await close_db(admin_connection)
