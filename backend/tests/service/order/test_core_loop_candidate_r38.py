"""MiniApp 核心闭环 r38：后台取消与优惠券应用并发一致性。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.database import close_db, init_db
from app.models.coupon import CouponTemplate, CouponType
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.repository.base import DatabaseHandle
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.coupon import CouponService
from app.service.coupon.inventory import CouponInventoryService
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.order.serialization import OrderSerializationService
from app.service.order.status_flow import OrderAdminStatusService
from app.service.order.timeline import OrderTimelineService
from tests.helpers.legacy_order_catalog import (
    LegacyOrderInventoryRepo,
    LegacyOrderProductRepo,
)

MOBILE = "13800003038"
OPENID = "admin_cancel_coupon_r38_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_admin_cancel_coupon_r38_001"
COUPON_ID = "coupon_admin_cancel_r38_001"
COUPON_FEN = 500
ORDER_AMOUNT_FEN = 10_000


def _build_coupon_service(handle: DatabaseHandle) -> CouponService:
    """为单个请求连接构建真实优惠券服务。"""
    return CouponService(
        template_repo=CouponTemplateRepo(handle),
        inventory_repo=CouponInventoryRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
        order_repo=OrderRepo(handle),
        inventory_service=CouponInventoryService(handle),
    )


def _build_admin_service(handle: DatabaseHandle) -> OrderAdminStatusService:
    """为单个请求连接构建真实后台订单状态服务。"""
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


async def _seed_order_member_and_coupon(connection: aiosqlite.Connection) -> None:
    """写入待支付订单、会员身份和一张未核销优惠券。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '后台取消券竞态会员', 'high', 1)",
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
        "INSERT INTO member_balance (mobile, stored_value_fen, points) VALUES (?, 0, 0)",
        (MOBILE,),
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
                        "product_id": "p_admin_cancel_coupon_r38",
                        "title": "后台取消券竞态蛋糕",
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
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id="cg_admin_cancel_coupon_r38_001",
            name="后台取消券竞态测试券",
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
            coupon_group_id="cg_admin_cancel_coupon_r38_001",
            title="后台取消券竞态测试券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id="cg_admin_cancel_coupon_r38_001",
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()


async def _attempt_coupon(
    service: CouponService,
    handle: DatabaseHandle,
) -> tuple[str, str]:
    """在独立请求连接中应用券并显式提交。"""
    try:
        result = await service.apply_coupon(
            ORDER_ID,
            user_id=USER_ID,
            coupon_id=COUPON_ID,
        )
        await handle.commit()
        return "ok", str(result["paymentStatus"])
    except ValueError as exc:
        await handle.rollback()
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        await handle.rollback()
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_admin_cancel(
    service: OrderAdminStatusService,
) -> tuple[str, str]:
    """在生产后台应用服务等价事务中取消订单。"""
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


async def _read_final_state(
    connection: aiosqlite.Connection,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """读取订单、券生命周期和后台取消事件。"""
    order_rows = await connection.execute_fetchall(
        "SELECT status, payment FROM orders WHERE id = ?",
        (ORDER_ID,),
    )
    coupon_rows = await connection.execute_fetchall(
        "SELECT coupon_id, status, order_no FROM coupon_inventory "
        "WHERE coupon_id = ? ORDER BY id",
        (COUPON_ID,),
    )
    event_rows = await connection.execute_fetchall(
        "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
        (ORDER_ID,),
    )
    return order_rows, coupon_rows, event_rows


def _assert_clean_coupon_and_cancel(
    order_rows: list[dict[str, object]],
    coupon_rows: list[dict[str, object]],
    event_rows: list[dict[str, object]],
) -> None:
    """取消后只能清掉快照，券仍可重新使用且只有一个取消事件。"""
    assert len(order_rows) == 1
    assert str(order_rows[0]["status"]) == "cancelled"
    payment = json.loads(str(order_rows[0]["payment"]))
    assert str(payment["status"]) == "unpaid"
    assert str(payment.get("couponId", "")) == ""
    assert int(payment.get("couponFen", 0)) == 0
    assert int(payment.get("remainFen", ORDER_AMOUNT_FEN)) == ORDER_AMOUNT_FEN
    assert len(coupon_rows) == 1
    assert str(coupon_rows[0]["status"]) == CouponStatus.TAKE
    assert str(coupon_rows[0]["order_no"] or "") == ""
    assert len(event_rows) == 1
    assert str(event_rows[0]["status"]) == "cancelled"
    assert str(event_rows[0]["operator"]) == "admin"


@pytest.mark.asyncio
@pytest.mark.parametrize("winner", ["coupon", "admin"])
async def test_admin_cancel_and_coupon_application_race_clears_snapshot(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    winner: str,
) -> None:
    """券快照与后台取消并发后只能留下干净取消事实。"""
    database_path = tmp_path / f"admin-cancel-coupon-{winner}-r38.db"
    coupon_connection = await init_db(str(database_path))
    admin_connection = await init_db(str(database_path))
    coupon_handle = DatabaseHandle(coupon_connection)
    admin_handle = DatabaseHandle(admin_connection)
    try:
        await _seed_order_member_and_coupon(coupon_connection)
        coupon_service = _build_coupon_service(coupon_handle)
        admin_service = _build_admin_service(admin_handle)

        initial_read_barrier = asyncio.Barrier(2)
        coupon_committed = asyncio.Event()
        admin_committed = asyncio.Event()
        winner_committed = coupon_committed if winner == "coupon" else admin_committed
        coupon_handle_key = id(coupon_handle)
        first_read_handles: set[int] = set()
        original_get_order = OrderRepo.get_order

        async def synchronized_initial_order_read(
            repo: OrderRepo,
            order_id: str,
        ):
            """同步两个请求首次读取旧订单并固定提交顺序。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if handle_key not in first_read_handles:
                first_read_handles.add(handle_key)
                await asyncio.wait_for(initial_read_barrier.wait(), timeout=5)
                role = "coupon" if handle_key == coupon_handle_key else "admin"
                if role != winner:
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(OrderRepo, "get_order", synchronized_initial_order_read)

        async def run_coupon() -> tuple[str, str]:
            result = await _attempt_coupon(coupon_service, coupon_handle)
            coupon_committed.set()
            return result

        async def run_admin() -> tuple[str, str]:
            result = await _attempt_admin_cancel(admin_service)
            admin_committed.set()
            return result

        coupon_result, admin_result = await asyncio.gather(
            run_coupon(),
            run_admin(),
        )
        admin_retry_result = None
        if winner == "coupon" and admin_result[0] == "locked":
            admin_retry_result = await _attempt_admin_cancel(admin_service)

        order_rows, coupon_rows, event_rows = await _read_final_state(coupon_connection)
        _assert_clean_coupon_and_cancel(order_rows, coupon_rows, event_rows)
        if winner == "coupon":
            assert coupon_result == ("ok", "partial")
            assert admin_result[0] in {"ok", "locked"}
            if admin_result[0] == "locked":
                assert admin_retry_result == ("ok", "cancelled")
            else:
                assert admin_result == ("ok", "cancelled")
                assert admin_retry_result is None
        else:
            assert admin_result == ("ok", "cancelled")
            assert coupon_result[0] in {"conflict", "locked"}
            assert admin_retry_result is None
    finally:
        await close_db(admin_connection)
        await close_db(coupon_connection)
