"""MiniApp 核心闭环 r30：并发应用不同优惠券只能有一个快照胜出。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.database import close_db, init_db
from app.models.coupon import CouponTemplate, CouponType
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.models.order import Order, OrderStatus
from app.repository.base import DatabaseHandle
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.order_repo import OrderRepo
from app.service.coupon import CouponService
from app.service.coupon.inventory import CouponInventoryService
from app.service.order.payment_state import build_initial_payment, now_text

ORDER_ID = "order_coupon_snapshot_race_001"
USER_ID = "wx_coupon_snapshot_race_001"
OPENID = "coupon_snapshot_race_001"
MOBILE = "13800003030"
ORDER_AMOUNT_FEN = 10_000
COUPON_IDS = ("coupon_snapshot_race_a", "coupon_snapshot_race_b")
COUPON_FENS = (500, 1_000)


def _build_coupon_service(handle: DatabaseHandle) -> CouponService:
    """为单个请求连接构建真实优惠券服务。"""
    return CouponService(
        template_repo=CouponTemplateRepo(handle),
        inventory_repo=CouponInventoryRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
        order_repo=OrderRepo(handle),
        inventory_service=CouponInventoryService(handle),
    )


async def _seed_order_and_two_coupons(connection: aiosqlite.Connection) -> None:
    """写入待支付订单、会员身份和两张不同面额可用券。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '并发选券会员', 'high', 1)",
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
        "VALUES (?, 0, 0)",
        (MOBILE,),
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
                        "product_id": "p_coupon_snapshot_race",
                        "title": "并发选券竞态蛋糕",
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
    template_repo = CouponTemplateRepo(connection)
    inventory_repo = CouponInventoryRepo(connection)
    for index, (coupon_id, coupon_fen) in enumerate(
        zip(COUPON_IDS, COUPON_FENS, strict=True),
        start=1,
    ):
        template_id = f"cg_coupon_snapshot_race_{index}"
        await template_repo.upsert_from_youzan(
            CouponTemplate(
                id=template_id,
                name=f"并发选券测试券{index}",
                coupon_type=CouponType.FULL_REDUCTION,
                threshold_fen=3_000,
                value_fen=coupon_fen,
                valid_from="2026-08-01",
                valid_until="2026-12-31",
            )
        )
        await inventory_repo.insert(
            CouponInventoryEntry(
                coupon_id=coupon_id,
                status=CouponStatus.TAKE,
                mobile=MOBILE,
                coupon_group_id=template_id,
                title=f"并发选券测试券{index}",
                value_fen=coupon_fen,
                source=LedgerSource.IMPORT,
                occurred_at=f"2026-08-0{index} 09:00:00",
                template_id=template_id,
                valid_from="2026-08-01",
                valid_until="2026-12-31",
            )
        )
    await connection.commit()


@pytest.mark.asyncio
async def test_concurrent_different_coupon_applications_only_one_succeeds(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两个请求读到同一旧快照时，只允许一个券金额成为订单事实。"""
    database_path = tmp_path / "coupon-snapshot-race.db"
    connection_a = await init_db(str(database_path))
    connection_b = await init_db(str(database_path))
    handle_a = DatabaseHandle(connection_a)
    handle_b = DatabaseHandle(connection_b)
    try:
        await _seed_order_and_two_coupons(connection_a)
        service_a = _build_coupon_service(handle_a)
        service_b = _build_coupon_service(handle_b)

        both_initial_snapshots_read = asyncio.Event()
        synchronized_handles: set[int] = set()
        handle_keys = {id(handle_a), id(handle_b)}
        original_get_order = OrderRepo.get_order

        async def read_same_initial_snapshot(
            repo: OrderRepo,
            order_id: str,
        ):
            """让两个请求都在任何券快照写入前读到 unpaid 订单。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if order_id == ORDER_ID and handle_key in handle_keys:
                synchronized_handles.add(handle_key)
                if len(synchronized_handles) == 2:
                    both_initial_snapshots_read.set()
                if len(synchronized_handles) <= 2:
                    await asyncio.wait_for(
                        both_initial_snapshots_read.wait(),
                        timeout=5,
                    )
            return order

        monkeypatch.setattr(OrderRepo, "get_order", read_same_initial_snapshot)

        async def apply_coupon(
            service: CouponService,
            handle: DatabaseHandle,
            coupon_id: str,
        ) -> tuple[str, dict | str]:
            """模拟一个独立 HTTP 请求并提交其数据库事务。"""
            try:
                result = await service.apply_coupon(
                    ORDER_ID,
                    user_id=USER_ID,
                    coupon_id=coupon_id,
                )
                await handle.commit()
                return "ok", result
            except ValueError as exc:
                await handle.rollback()
                return "conflict", str(exc)
            except sqlite3.OperationalError as exc:
                await handle.rollback()
                if "locked" not in str(exc).lower():
                    raise
                return "locked", str(exc)

        results = await asyncio.gather(
            apply_coupon(service_a, handle_a, COUPON_IDS[0]),
            apply_coupon(service_b, handle_b, COUPON_IDS[1]),
        )

        order_rows = await connection_a.execute_fetchall(
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        )
        assert len(order_rows) == 1
        payment = json.loads(str(order_rows[0]["payment"]))
        successful_results = [result for outcome, result in results if outcome == "ok"]
        conflict_messages = [
            result for outcome, result in results if outcome == "conflict"
        ]

        assert [
            (
                str(result["couponId"]),
                int(result["couponFen"]),
                int(result["remainFen"]),
            )
            for result in successful_results
        ] == [
            (
                str(payment["couponId"]),
                int(payment["couponFen"]),
                int(payment["remainFen"]),
            )
        ]
        assert sorted(outcome for outcome, _result in results) == [
            "conflict",
            "ok",
        ], results
        assert len(successful_results) == 1
        assert str(order_rows[0]["status"]) == "pending"
        assert str(payment["status"]) == "partial"
        assert str(payment["couponId"]) == str(successful_results[0]["couponId"])
        assert int(payment["couponFen"]) == int(successful_results[0]["couponFen"])
        assert int(payment["remainFen"]) == int(successful_results[0]["remainFen"])
        assert len(conflict_messages) == 1
        assert str(conflict_messages[0]) == "订单支付状态更新冲突"
    finally:
        await close_db(connection_b)
        await close_db(connection_a)
