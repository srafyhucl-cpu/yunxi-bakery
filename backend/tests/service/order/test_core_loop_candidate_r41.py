"""MiniApp 核心闭环 r41：用户取消与微信全额退款通知竞态。"""

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
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.coupon import CouponService
from app.service.coupon.inventory import CouponInventoryService
from app.service.order.cancellation import OrderCancellationService
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_runtime import OrderPaymentRuntimeService
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

MOBILE = "13800003041"
OPENID = "cancel_refund_notify_race_r41_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_cancel_refund_race_r41_001"
COUPON_ID = "coupon_cancel_refund_race_r41_001"
TEMPLATE_ID = "template_cancel_refund_race_r41_001"
EVENT_ID = "EV-cancel-refund-race-r41-001"
OUT_REFUND_NO = "R-cancel-refund-race-r41-001"
REFUND_ID = "refund-cancel-refund-race-r41-001"
TRANSACTION_ID = "4200000000202609251234567899"
ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 1_000
BALANCE_FEN = 2_000
EXTERNAL_FEN = ORDER_AMOUNT_FEN - COUPON_FEN - BALANCE_FEN
INITIAL_BALANCE_FEN = 20_000


class _MockRemainderWechat:
    """只为组合支付构造本地 mock 尾款，不访问微信网络。"""

    def is_ready(self) -> bool:
        return False


def _build_member_service(handle: DatabaseHandle) -> MemberBalanceService:
    """构建真实会员余额服务。"""
    return MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )


def _build_coupon_service(handle: DatabaseHandle) -> CouponService:
    """构建真实优惠券服务。"""
    return CouponService(
        template_repo=CouponTemplateRepo(handle),
        inventory_repo=CouponInventoryRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
        order_repo=OrderRepo(handle),
        inventory_service=CouponInventoryService(handle),
    )


def _build_payment_service(
    handle: DatabaseHandle,
) -> StoredValueOrderPaymentService:
    """构建真实余额与组合支付服务。"""
    return StoredValueOrderPaymentService(
        order_repo=OrderRepo(handle),
        member_service=_build_member_service(handle),
        wechat_pay_service=_MockRemainderWechat(),
    )


def _build_cancellation_service(
    handle: DatabaseHandle,
) -> OrderCancellationService:
    """构建生产等价事务边界的用户取消服务。"""
    order_repo = OrderRepo(handle)
    payment_service = _build_payment_service(handle)
    return OrderCancellationService(
        order_repo=order_repo,
        inventory_service=OrderInventoryService(
            product_repo=LegacyOrderProductRepo(handle),
            inventory_repo=LegacyOrderInventoryRepo(handle),
        ),
        timeline_service=OrderTimelineService(
            serialization_service=OrderSerializationService(),
            event_repo=OrderEventRepo(handle),
        ),
        stored_value_service=StoredValueService(
            member_service=_build_member_service(handle),
            payment_service=payment_service,
        ),
    )


def _refund_transaction() -> dict:
    """构造与组合支付外部腿完全匹配的全额退款事实。"""
    return {
        "mchid": "mch-r41",
        "out_trade_no": ORDER_ID,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": OUT_REFUND_NO,
        "refund_id": REFUND_ID,
        "refund_status": "SUCCESS",
        "success_time": "2026-09-25T12:05:00+08:00",
        "amount": {
            "total": EXTERNAL_FEN,
            "refund": EXTERNAL_FEN,
            "payer_total": EXTERNAL_FEN,
            "payer_refund": EXTERNAL_FEN,
        },
    }


def _notify_body() -> bytes:
    """构造本地退款通知入口载荷。"""
    return json.dumps(
        {
            "id": EVENT_ID,
            "event_type": "REFUND.SUCCESS",
            "resource": {"kind": "refund"},
        }
    ).encode("utf-8")


async def _seed_combined_order(connection: aiosqlite.Connection) -> None:
    """写入会员、券、余额和已扣余额的组合支付 partial 订单。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '取消退款竞态会员', 'high', 1)",
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
    await OrderRepo(connection).create_order(
        Order(
            id=ORDER_ID,
            session_id=f"session_{ORDER_ID}",
            channel="miniapp",
            user_id=USER_ID,
            products="[]",
            total_amount=ORDER_AMOUNT_FEN / 100,
            delivery="{}",
            payment=json.dumps(build_initial_payment(now_text()), ensure_ascii=False),
            status=OrderStatus.PENDING,
            remark="",
            created_at=now_text(),
            updated_at=now_text(),
        )
    )
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=TEMPLATE_ID,
            name="取消退款竞态测试券",
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
            coupon_group_id=TEMPLATE_ID,
            title="取消退款竞态测试券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id=TEMPLATE_ID,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()

    coupon_service = _build_coupon_service(DatabaseHandle(connection))
    await coupon_service.apply_coupon(
        ORDER_ID,
        user_id=USER_ID,
        coupon_id=COUPON_ID,
    )
    payment_service = _build_payment_service(DatabaseHandle(connection))
    await payment_service.prepare_combined_payment(
        ORDER_ID,
        user_id=USER_ID,
        balance_fen=BALANCE_FEN,
    )
    await connection.commit()


async def _attempt_cancel(
    service: OrderCancellationService,
) -> tuple[str, str]:
    """在生产应用服务等价事务中执行用户取消。"""
    try:
        async with service._order_repo.transaction():
            result = await service.cancel_user_order(ORDER_ID, user_id=USER_ID)
        return "ok", str(result["status"])
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_refund(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, dict | str]:
    """执行真实退款通知 intake 与补偿事务。"""
    try:
        result = await service.handle_wechat_refund_notify(
            raw_body=raw_body,
            headers={},
        )
        return "ok", result
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["cancel", "refund"])
async def test_cancel_and_refund_notify_race_preserves_assets(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    first_winner: str,
) -> None:
    """两种提交顺序都只能形成一次余额退款、一次退款事实和一张可用券。"""
    database_path = tmp_path / f"cancel-refund-notify-race-{first_winner}-r41.db"
    cancel_connection = await init_db(str(database_path))
    refund_connection = await init_db(str(database_path))
    cancel_handle = DatabaseHandle(cancel_connection)
    refund_handle = DatabaseHandle(refund_connection)
    try:
        await _seed_combined_order(cancel_connection)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-r41")
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_verify_wechat_notify_signature",
            lambda self, raw_body, headers: True,
        )
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_decrypt_wechat_resource",
            lambda self, resource: _refund_transaction(),
        )
        cancel_service = _build_cancellation_service(cancel_handle)
        refund_service = OrderPaymentRuntimeService(
            OrderRepo(refund_handle),
            _MockRemainderWechat(),
            OrderEventRepo(refund_handle),
        )
        raw_body = _notify_body()

        both_snapshots_read = asyncio.Event()
        winner_committed = asyncio.Event()
        observed_handles: set[int] = set()
        cancel_handle_key = id(cancel_handle)
        refund_handle_key = id(refund_handle)
        original_get_order = OrderRepo.get_order

        async def read_old_snapshot_together(
            repo: OrderRepo,
            order_id: str,
        ):
            """让两个事务先读同一 partial 快照，再只允许指定胜者提交。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if (
                order_id == ORDER_ID
                and handle_key in {cancel_handle_key, refund_handle_key}
                and handle_key not in observed_handles
            ):
                observed_handles.add(handle_key)
                if len(observed_handles) == 2:
                    both_snapshots_read.set()
                await asyncio.wait_for(both_snapshots_read.wait(), timeout=5)
                role = "cancel" if handle_key == cancel_handle_key else "refund"
                if role != first_winner:
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(OrderRepo, "get_order", read_old_snapshot_together)

        async def run_cancel() -> tuple[str, str]:
            result = await _attempt_cancel(cancel_service)
            if first_winner == "cancel":
                winner_committed.set()
            return result

        async def run_refund() -> tuple[str, dict | str]:
            result = await _attempt_refund(refund_service, raw_body)
            if first_winner == "refund":
                winner_committed.set()
            return result

        cancel_result, refund_result = await asyncio.gather(
            run_cancel(),
            run_refund(),
        )

        cancel_retry_result = cancel_result
        refund_retry_count = 0
        if cancel_retry_result[0] != "ok":
            assert cancel_retry_result[0] == "locked"
            cancel_retry_result = await _attempt_cancel(cancel_service)
        assert cancel_retry_result == ("ok", OrderStatus.CANCELLED.value)
        if refund_result[0] != "ok":
            assert refund_result[0] == "locked"
            await refund_connection.execute(
                "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
                "WHERE message_key = ? AND status = 'failed'",
                (f"wechat_pay_notify:{EVENT_ID}",),
            )
            await refund_connection.commit()
            refund_result = await _attempt_refund(refund_service, raw_body)
            refund_retry_count = 1
        assert refund_result[0] == "ok"

        duplicate_refund = await _attempt_refund(refund_service, raw_body)
        await refund_handle.commit()

        order_rows = await cancel_connection.execute_fetchall(
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        )
        balance_rows = await cancel_connection.execute_fetchall(
            "SELECT stored_value_fen, points FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        )
        balance_ledger_rows = await cancel_connection.execute_fetchall(
            "SELECT unique_id, amount_fen FROM balance_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        )
        coupon_rows = await cancel_connection.execute_fetchall(
            "SELECT status, order_no, deducted_fen FROM coupon_inventory "
            "WHERE coupon_id = ? ORDER BY id",
            (COUPON_ID,),
        )
        refund_rows = await cancel_connection.execute_fetchall(
            "SELECT out_refund_no, transaction_id, payer_refund_fen "
            "FROM wechat_refund_events WHERE order_id = ?",
            (ORDER_ID,),
        )
        event_rows = await cancel_connection.execute_fetchall(
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        )
        inbox_rows = await cancel_connection.execute_fetchall(
            "SELECT status, attempt_count FROM inbox_events WHERE message_key = ?",
            (f"wechat_pay_notify:{EVENT_ID}",),
        )
        points_rows = await cancel_connection.execute_fetchall(
            "SELECT unique_id FROM points_ledger WHERE biz_id = ?",
            (ORDER_ID,),
        )

        assert observed_handles == {cancel_handle_key, refund_handle_key}
        assert duplicate_refund == (
            "ok",
            {"duplicate": True, "kind": "duplicate"},
        )
        assert len(order_rows) == 1
        assert str(order_rows[0]["status"]) == OrderStatus.CANCELLED.value
        payment = json.loads(str(order_rows[0]["payment"]))
        assert str(payment["status"]) == "partial"
        assert str(payment.get("couponId", "")) == ""
        assert int(payment.get("couponFen", 0)) == 0
        assert int(payment["balanceFen"]) == BALANCE_FEN
        assert int(payment["externalPaidFen"]) == EXTERNAL_FEN
        assert str(payment["refundStatus"]) == "full"
        assert int(payment["refundFen"]) == EXTERNAL_FEN
        assert [dict(row) for row in balance_rows] == [
            {"stored_value_fen": INITIAL_BALANCE_FEN, "points": 0}
        ]
        assert [dict(row) for row in balance_ledger_rows] == [
            {"unique_id": f"combined_pay:{ORDER_ID}", "amount_fen": -BALANCE_FEN},
            {"unique_id": f"order_refund:{ORDER_ID}", "amount_fen": BALANCE_FEN},
        ]
        assert [dict(row) for row in coupon_rows] == [
            {"status": CouponStatus.TAKE, "order_no": "", "deducted_fen": 0}
        ]
        assert [dict(row) for row in refund_rows] == [
            {
                "out_refund_no": OUT_REFUND_NO,
                "transaction_id": TRANSACTION_ID,
                "payer_refund_fen": EXTERNAL_FEN,
            }
        ]
        assert [dict(row) for row in event_rows] == [
            {"status": OrderStatus.CANCELLED.value, "operator": f"miniapp:{USER_ID}"}
        ]
        assert [dict(row) for row in inbox_rows] == [
            {
                "status": "processed",
                "attempt_count": refund_retry_count + 1,
            }
        ]
        assert points_rows == []
    finally:
        await close_db(refund_connection)
        await close_db(cancel_connection)
