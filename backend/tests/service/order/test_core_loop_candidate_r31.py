"""MiniApp 核心闭环 r31：优惠券应用与余额支付并发候选排除。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.models.coupon import CouponTemplate, CouponType
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.models.order import Order, OrderStatus
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.base import DatabaseHandle
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_repo import OrderRepo
from app.service.coupon import CouponService
from app.service.coupon.inventory import CouponInventoryService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
)

ORDER_ID = "order_coupon_balance_race_001"
USER_ID = "wx_coupon_balance_race_001"
OPENID = "coupon_balance_race_001"
MOBILE = "13800003031"
ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 500
COUPON_ID = "coupon_balance_race_001"
INITIAL_BALANCE_FEN = 20_000


def _build_coupon_service(handle: DatabaseHandle) -> CouponService:
    """为单个请求连接构建真实优惠券服务。"""
    return CouponService(
        template_repo=CouponTemplateRepo(handle),
        inventory_repo=CouponInventoryRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
        order_repo=OrderRepo(handle),
        inventory_service=CouponInventoryService(handle),
    )


def _build_payment_service(handle: DatabaseHandle) -> StoredValueOrderPaymentService:
    """为单个请求连接构建真实余额支付服务。"""
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )
    return StoredValueOrderPaymentService(
        order_repo=OrderRepo(handle),
        member_service=member_service,
    )


async def _seed_order_member_and_coupon(connection: aiosqlite.Connection) -> None:
    """写入待支付订单、会员身份、余额和一张可用券。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '券与余额并发会员', 'high', 1)",
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
        "INSERT INTO member_balance (mobile, stored_value_fen, points) "
        "VALUES (?, ?, 0)",
        (MOBILE, INITIAL_BALANCE_FEN),
    )
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id, status) "
        "VALUES (?, 'miniapp', ?, 'active')",
        (f"session_{ORDER_ID}", USER_ID),
    )
    await OrderRepo(connection).create_order(
        Order(
            id=ORDER_ID,
            session_id=f"session_{ORDER_ID}",
            channel="miniapp",
            user_id=USER_ID,
            products=json.dumps(
                [
                    {
                        "product_id": "p_coupon_balance_race",
                        "title": "券与余额并发竞态蛋糕",
                        "price_fen": ORDER_AMOUNT_FEN,
                        "quantity": 1,
                        "inventory_reserved": False,
                    }
                ],
                ensure_ascii=False,
            ),
            total_amount=ORDER_AMOUNT_FEN / 100,
            delivery=json.dumps({}, ensure_ascii=False),
            payment=json.dumps(build_initial_payment(now_text()), ensure_ascii=False),
            status=OrderStatus.PENDING,
            remark="",
            created_at=now_text(),
            updated_at=now_text(),
        )
    )
    template_id = "cg_coupon_balance_race_001"
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=template_id,
            name="券与余额并发测试券",
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
            title="券与余额并发测试券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id=template_id,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()


async def _apply_coupon_and_commit(
    service: CouponService,
    handle: DatabaseHandle,
) -> tuple[str, dict | str]:
    """模拟独立优惠券 HTTP 请求并提交外层数据库事务。"""
    try:
        result = await service.apply_coupon(
            ORDER_ID,
            user_id=USER_ID,
            coupon_id=COUPON_ID,
        )
        await handle.commit()
        return "ok", result
    except ValueError as exc:
        await handle.rollback()
        return "conflict", str(exc)


async def _attempt_payment(
    service: StoredValueOrderPaymentService,
    payment_mode: str,
) -> tuple[str, dict | str]:
    """模拟独立余额支付 HTTP 请求。"""
    try:
        if payment_mode == "balance":
            result = await service.pay_order_with_balance(
                ORDER_ID,
                user_id=USER_ID,
            )
        else:
            result = await service.prepare_combined_payment(
                ORDER_ID,
                user_id=USER_ID,
                balance_fen=2_000,
            )
        return "ok", result
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


@pytest.mark.asyncio
@pytest.mark.parametrize("payment_mode", ["balance", "combined"])
async def test_coupon_application_wins_before_stale_balance_payment(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    payment_mode: str,
) -> None:
    """券先提交后，持旧快照的余额支付只能回滚且不得改写支付事实。"""
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
    database_path = tmp_path / f"coupon-{payment_mode}-payment-race.db"
    connection_a = await init_db(str(database_path))
    connection_b = await init_db(str(database_path))
    coupon_handle = DatabaseHandle(connection_a)
    payment_handle = DatabaseHandle(connection_b)
    try:
        await _seed_order_member_and_coupon(connection_a)
        coupon_service = _build_coupon_service(coupon_handle)
        payment_service = _build_payment_service(payment_handle)
        coupon_committed = asyncio.Event()
        payment_snapshot_read = asyncio.Event()
        payment_read_count = 0
        payment_handle_key = id(payment_handle)
        original_get_order = OrderRepo.get_order

        async def ordered_stale_payment_read(repo: OrderRepo, order_id: str):
            """让支付读到旧快照后先提交券，再继续真实支付流程。"""
            nonlocal payment_read_count
            order = await original_get_order(repo, order_id)
            if order_id != ORDER_ID or id(repo._db) != payment_handle_key:
                return order
            payment_read_count += 1
            if payment_mode == "balance" or payment_read_count == 2:
                payment_snapshot_read.set()
                await asyncio.wait_for(coupon_committed.wait(), timeout=5)
            return order

        async def read_after_payment_snapshot(repo: OrderRepo, order_id: str):
            """确保券请求与支付事务内第二次读取基于同一个旧快照。"""
            order = await original_get_order(repo, order_id)
            if order_id == ORDER_ID and id(repo._db) != payment_handle_key:
                await asyncio.wait_for(payment_snapshot_read.wait(), timeout=5)
            return order

        monkeypatch.setattr(OrderRepo, "get_order", ordered_stale_payment_read)

        async def coordinated_get_order(repo: OrderRepo, order_id: str):
            """按请求连接分别同步旧快照读取顺序。"""
            if id(repo._db) == payment_handle_key:
                return await ordered_stale_payment_read(repo, order_id)
            return await read_after_payment_snapshot(repo, order_id)

        monkeypatch.setattr(OrderRepo, "get_order", coordinated_get_order)

        async def apply_coupon_first() -> tuple[str, dict | str]:
            """在支付恢复前完成券快照提交。"""
            result = await _apply_coupon_and_commit(coupon_service, coupon_handle)
            coupon_committed.set()
            return result

        coupon_result, payment_result = await asyncio.gather(
            apply_coupon_first(),
            _attempt_payment(payment_service, payment_mode),
        )
        coupon_outcome, coupon_value = coupon_result
        payment_outcome, payment_value = payment_result

        order_rows = await connection_a.execute_fetchall(
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        )
        balance_rows = await connection_a.execute_fetchall(
            "SELECT stored_value_fen FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        )
        ledger_rows = await connection_a.execute_fetchall(
            "SELECT unique_id FROM balance_ledger WHERE biz_id = ?",
            (ORDER_ID,),
        )
        coupon_rows = await connection_a.execute_fetchall(
            "SELECT coupon_id, status, order_no FROM coupon_inventory "
            "WHERE coupon_id = ? ORDER BY id",
            (COUPON_ID,),
        )

        assert coupon_outcome == "ok", coupon_result
        assert payment_outcome in {"conflict", "locked"}, payment_result
        assert len(order_rows) == 1
        payment = json.loads(str(order_rows[0]["payment"]))
        assert str(order_rows[0]["status"]) == "pending"
        assert str(payment["status"]) == "partial"
        assert str(payment["method"]) == "combined"
        assert str(payment["couponId"]) == COUPON_ID
        assert int(payment["couponFen"]) == COUPON_FEN
        assert int(payment["remainFen"]) == ORDER_AMOUNT_FEN - COUPON_FEN
        assert int(payment.get("balanceFen", 0)) == 0
        assert int(balance_rows[0]["stored_value_fen"]) == INITIAL_BALANCE_FEN
        assert ledger_rows == []
        assert len(coupon_rows) == 1
        assert str(coupon_rows[0]["status"]) == CouponStatus.TAKE
        assert str(coupon_rows[0]["order_no"] or "") == ""
        assert isinstance(coupon_value, dict)
        assert int(coupon_value["remainFen"]) == int(payment["remainFen"])
        assert payment_value is not None
    finally:
        await close_db(connection_b)
        await close_db(connection_a)
