"""MiniApp 核心闭环 r36：退款终态与后台履约状态并发候选复核。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.models.order import Order, OrderStatus
from app.repository.base import DatabaseHandle
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.order.inventory import OrderInventoryService
from app.service.order.refund_notification import WechatRefundNotificationService
from app.service.order.serialization import OrderSerializationService
from app.service.order.status_flow import OrderAdminStatusService
from app.service.order.timeline import OrderTimelineService
from app.service.order.wechat_normalizers import RefundNotify
from tests.helpers.legacy_order_catalog import (
    LegacyOrderInventoryRepo,
    LegacyOrderProductRepo,
)

ORDER_ID = "order_refund_fulfillment_race_r36_001"
USER_ID = "wx_refund_fulfillment_race_r36_001"
ORDER_AMOUNT_FEN = 10_000
TRANSACTION_ID = "4200000000202609251234567893"
REFUND_ID = "refund-r36-001"
OUT_REFUND_NO = "R-r36-001"


def _build_admin_service(handle: DatabaseHandle) -> OrderAdminStatusService:
    """构建真实后台订单状态服务。"""
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


async def _seed_paid_order(connection: aiosqlite.Connection) -> None:
    """写入已支付、待履约且无资产腿的合成订单。"""
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id) VALUES (?, 'miniapp', ?)",
        (f"session_{ORDER_ID}", USER_ID),
    )
    await OrderRepo(connection).create_order(
        Order(
            id=ORDER_ID,
            session_id=f"session_{ORDER_ID}",
            channel="miniapp",
            user_id=USER_ID,
            products="[]",
            total_amount=ORDER_AMOUNT_FEN / 100,
            delivery="{}",
            payment=json.dumps(
                {
                    "status": "paid",
                    "method": "wechat",
                    "paidAt": "2026-09-25 10:00:00",
                    "transactionId": TRANSACTION_ID,
                    "externalPaidFen": ORDER_AMOUNT_FEN,
                    "couponFen": 0,
                    "balanceFen": 0,
                    "pointsFen": 0,
                    "pointsUsed": 0,
                },
                ensure_ascii=False,
            ),
            status=OrderStatus.CONFIRMED,
            remark="",
            created_at="2026-09-25 09:00:00",
            updated_at="2026-09-25 10:00:00",
        )
    )
    await connection.commit()


def _refund_notify() -> RefundNotify:
    """构造与支付快照完全匹配的全额退款通知。"""
    return RefundNotify(
        mchid="mch-r36",
        out_trade_no=ORDER_ID,
        transaction_id=TRANSACTION_ID,
        out_refund_no=OUT_REFUND_NO,
        refund_id=REFUND_ID,
        refund_status="SUCCESS",
        success_time="2026-09-25T10:05:00+08:00",
        total_fen=ORDER_AMOUNT_FEN,
        refund_fen=ORDER_AMOUNT_FEN,
        payer_total_fen=ORDER_AMOUNT_FEN,
        payer_refund_fen=ORDER_AMOUNT_FEN,
        user_received_account="微信支付",
    )


@pytest.mark.asyncio
async def test_refund_terminal_blocks_stale_admin_fulfillment_update(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """退款先提交时，后台旧快照不得把全额退款订单推进到制作中。"""
    database_path = tmp_path / "refund-fulfillment-race-r36.db"
    admin_connection = await init_db(str(database_path))
    refund_connection = await init_db(str(database_path))
    admin_handle = DatabaseHandle(admin_connection)
    refund_handle = DatabaseHandle(refund_connection)
    try:
        await _seed_paid_order(admin_connection)
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-r36")
        admin_service = _build_admin_service(admin_handle)
        refund_service = WechatRefundNotificationService(OrderRepo(refund_handle))
        admin_old_snapshot_read = asyncio.Event()
        refund_committed = asyncio.Event()
        admin_handle_key = id(admin_handle)
        original_get_order = OrderRepo.get_order

        async def read_old_admin_snapshot(repo: OrderRepo, order_id: str):
            """让后台先读到无退款快照，再等待退款事务提交。"""
            order = await original_get_order(repo, order_id)
            if (
                order_id == ORDER_ID
                and id(repo._db) == admin_handle_key
                and not admin_old_snapshot_read.is_set()
            ):
                admin_old_snapshot_read.set()
                await asyncio.wait_for(refund_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(OrderRepo, "get_order", read_old_admin_snapshot)

        async def run_refund() -> dict:
            """提交真实全额退款事实。"""
            result = await refund_service.apply_refund_notify(_refund_notify())
            refund_committed.set()
            return result

        async def run_admin() -> tuple[str, str]:
            """在独立请求事务中推进后台履约状态。"""
            try:
                async with admin_service._order_repo.transaction():
                    result = await admin_service.update_admin_order_status(
                        ORDER_ID, "making"
                    )
                return "ok", str(result["status"])
            except ValueError as exc:
                return "conflict", str(exc)
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                return "locked", str(exc)

        refund_result, admin_result = await asyncio.gather(run_refund(), run_admin())

        order = await OrderRepo(admin_connection).get_order(ORDER_ID)
        assert refund_result["kind"] == "acknowledged"
        assert order is not None
        final_payment = json.loads(order.payment)
        assert admin_result[0] in {"locked", "conflict"}
        assert order.status == OrderStatus.CONFIRMED
        assert final_payment["refundStatus"] == "full"
    finally:
        await close_db(refund_connection)
        await close_db(admin_connection)
