"""MiniApp 核心闭环 r49：跨订单共享微信交易号并发候选复核。"""

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
from app.service.order import notify_intake
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
)

TRANSACTION_ID = "4200000000202609251234567949"
ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 1_000
BALANCE_FEN = 2_000
EXTERNAL_FEN = ORDER_AMOUNT_FEN - COUPON_FEN - BALANCE_FEN
INITIAL_BALANCE_FEN = 20_000
EXPECTED_AWARD_POINTS = EXTERNAL_FEN // 100
MCH_ID = "mch-cross-order-transaction-r49"
APP_ID = "appid-cross-order-transaction-r49"


class _LocalWechatPay:
    """为通知运行时提供不触网的成功时间格式化。"""

    def is_ready(self) -> bool:
        return False

    def format_success_time(self, value: str) -> str:
        return "2026-09-25 14:00:00"


def _member_service(handle: DatabaseHandle) -> MemberBalanceService:
    """构建真实会员余额服务。"""
    return MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )


def _coupon_service(handle: DatabaseHandle) -> CouponService:
    """构建真实优惠券服务。"""
    return CouponService(
        template_repo=CouponTemplateRepo(handle),
        inventory_repo=CouponInventoryRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
        order_repo=OrderRepo(handle),
        inventory_service=CouponInventoryService(handle),
    )


def _combined_service(handle: DatabaseHandle) -> StoredValueOrderPaymentService:
    """构建真实组合支付服务。"""
    return StoredValueOrderPaymentService(
        order_repo=OrderRepo(handle),
        member_service=_member_service(handle),
        wechat_pay_service=_LocalWechatPay(),
    )


def _runtime_service(handle: DatabaseHandle) -> OrderPaymentRuntimeService:
    """构建真实支付通知入口。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=_LocalWechatPay(),
        event_repo=OrderEventRepo(handle),
    )


def _payment_transaction(order_id: str) -> dict:
    """构造指定订单的支付成功通知，但两个通知共享同一微信交易号。"""
    return {
        "out_trade_no": order_id,
        "trade_state": "SUCCESS",
        "mchid": MCH_ID,
        "appid": APP_ID,
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T14:00:00+08:00",
    }


def _notify_body(event_id: str, order_id: str) -> bytes:
    """构造携带独立事件标识和订单号的本地通知外层载荷。"""
    return json.dumps(
        {
            "id": event_id,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {"kind": "payment", "order_id": order_id},
        },
        ensure_ascii=False,
    ).encode("utf-8")


async def _seed_order(
    connection: aiosqlite.Connection,
    *,
    suffix: str,
    mobile: str,
    user_id: str,
    order_id: str,
    coupon_id: str,
) -> None:
    """写入一套独立的会员、余额、订单和优惠券组合支付快照。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, ?, 'high', 1)",
        (f"cm_{suffix}", mobile, f"跨订单交易号会员{suffix}"),
    )
    await connection.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (
            f"cil_{suffix}",
            f"cm_{suffix}",
            user_id.removeprefix("wx_"),
            user_id.removeprefix("wx_"),
        ),
    )
    await connection.execute(
        "INSERT INTO member_balance (mobile, stored_value_fen, points) VALUES (?, ?, 0)",
        (mobile, INITIAL_BALANCE_FEN),
    )
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id, status) "
        "VALUES (?, 'miniapp', ?, 'active')",
        (f"session_{suffix}", user_id),
    )
    await OrderRepo(connection).create_order(
        Order(
            id=order_id,
            session_id=f"session_{suffix}",
            channel="miniapp",
            user_id=user_id,
            products="[]",
            total_amount=ORDER_AMOUNT_FEN / 100,
            delivery="{}",
            payment=json.dumps(
                build_initial_payment("2026-09-25 13:00:00"),
                ensure_ascii=False,
            ),
            status=OrderStatus.PENDING,
            created_at="2026-09-25 13:00:00",
            updated_at="2026-09-25 13:00:00",
        )
    )
    template_id = f"template_{suffix}"
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=template_id,
            name=f"跨订单交易号测试券{suffix}",
            coupon_type=CouponType.FULL_REDUCTION,
            threshold_fen=3_000,
            value_fen=COUPON_FEN,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await CouponInventoryRepo(connection).insert(
        CouponInventoryEntry(
            coupon_id=coupon_id,
            status=CouponStatus.TAKE,
            mobile=mobile,
            coupon_group_id=template_id,
            title=f"跨订单交易号测试券{suffix}",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id=template_id,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()

    handle = DatabaseHandle(connection)
    coupon_result = await _coupon_service(handle).apply_coupon(
        order_id,
        user_id=user_id,
        coupon_id=coupon_id,
    )
    assert coupon_result["paymentStatus"] == "partial"
    await connection.commit()
    combined_result = await _combined_service(handle).prepare_combined_payment(
        order_id,
        user_id=user_id,
        balance_fen=BALANCE_FEN,
    )
    assert combined_result["payment"]["status"] == "partial"
    await connection.commit()


async def _attempt_notify(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, dict | str]:
    """执行通知入口并区分业务冲突与 SQLite 瞬时锁冲突。"""
    try:
        result = await service.handle_wechat_payment_notify(
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


async def _retry_failed_notify(
    connection: aiosqlite.Connection,
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
    message_key: str,
) -> tuple[str, dict | str]:
    """按生产 inbox 路径重投跨订单交易号冲突。"""
    await connection.execute(
        "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
        "WHERE message_key = ? AND status = 'failed'",
        (message_key,),
    )
    await connection.commit()
    return await _attempt_notify(service, raw_body)


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["order_a", "order_b"])
async def test_same_transaction_cannot_pay_two_orders(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    first_winner: str,
) -> None:
    """同一微信交易号并发到达两个订单时只能绑定其中一个订单。"""
    database_path = tmp_path / f"cross-order-transaction-{first_winner}-r49.db"
    first_connection = await init_db(str(database_path))
    second_connection = await init_db(str(database_path))
    first_handle = DatabaseHandle(first_connection)
    second_handle = DatabaseHandle(second_connection)
    order_a = "order_cross_transaction_r49_a"
    order_b = "order_cross_transaction_r49_b"
    user_a = "wx_cross_transaction_r49_a"
    user_b = "wx_cross_transaction_r49_b"
    mobile_a = "13800003049"
    mobile_b = "13800003050"
    coupon_a = "coupon_cross_transaction_r49_a"
    coupon_b = "coupon_cross_transaction_r49_b"
    event_a = "EV-cross-transaction-r49-a"
    event_b = "EV-cross-transaction-r49-b"
    key_a = f"wechat_pay_notify:{event_a}"
    key_b = f"wechat_pay_notify:{event_b}"
    try:
        await _seed_order(
            first_connection,
            suffix="cross_transaction_r49_a",
            mobile=mobile_a,
            user_id=user_a,
            order_id=order_a,
            coupon_id=coupon_a,
        )
        await _seed_order(
            first_connection,
            suffix="cross_transaction_r49_b",
            mobile=mobile_b,
            user_id=user_b,
            order_id=order_b,
            coupon_id=coupon_b,
        )
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_verify_wechat_notify_signature",
            lambda self, raw_body, headers: True,
        )
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_decrypt_wechat_resource",
            lambda self, resource: _payment_transaction(str(resource["order_id"])),
        )
        raw_a = _notify_body(event_a, order_a)
        raw_b = _notify_body(event_b, order_b)
        service_a = _runtime_service(first_handle)
        service_b = _runtime_service(second_handle)

        both_claims_committed = asyncio.Event()
        committed_claims = 0
        original_claim_notify = notify_intake.claim_notify

        async def commit_claim_before_business(
            db,
            event_id: str,
            payload: dict | None = None,
            *,
            lease_seconds: int = notify_intake.DEFAULT_NOTIFY_LEASE_SECONDS,
        ) -> dict:
            """先提交两个 inbox claim，再让两个业务事务读取旧订单快照。"""
            nonlocal committed_claims
            claim = await original_claim_notify(
                db,
                event_id,
                payload,
                lease_seconds=lease_seconds,
            )
            await db.commit()
            committed_claims += 1
            if committed_claims == 2:
                both_claims_committed.set()
            await asyncio.wait_for(both_claims_committed.wait(), timeout=5)
            return claim

        monkeypatch.setattr(notify_intake, "claim_notify", commit_claim_before_business)

        first_snapshots_read = asyncio.Barrier(2)
        winner_committed = asyncio.Event()
        observed_handles: set[int] = set()
        first_handle_key = id(first_handle)
        second_handle_key = id(second_handle)
        original_get_order = OrderRepo.get_order

        async def read_old_snapshots_before_claim(
            repo: OrderRepo,
            order_id: str,
        ):
            """让两个通知先读各自旧快照，再按参数固定首胜者。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if (
                order_id in {order_a, order_b}
                and handle_key in {first_handle_key, second_handle_key}
                and handle_key not in observed_handles
            ):
                observed_handles.add(handle_key)
                await asyncio.wait_for(first_snapshots_read.wait(), timeout=5)
                role = "order_a" if handle_key == first_handle_key else "order_b"
                if role != first_winner:
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(OrderRepo, "get_order", read_old_snapshots_before_claim)

        async def run_a() -> tuple[str, dict | str]:
            result = await _attempt_notify(service_a, raw_a)
            if first_winner == "order_a":
                winner_committed.set()
            return result

        async def run_b() -> tuple[str, dict | str]:
            result = await _attempt_notify(service_b, raw_b)
            if first_winner == "order_b":
                winner_committed.set()
            return result

        result_a, result_b = await asyncio.gather(run_a(), run_b())
        winner_result = result_a if first_winner == "order_a" else result_b
        loser_result = result_b if first_winner == "order_a" else result_a
        assert winner_result[0] == "ok"
        assert loser_result[0] in {"locked", "conflict"}
        assert observed_handles == {first_handle_key, second_handle_key}

        loser_connection = (
            second_connection if first_winner == "order_a" else first_connection
        )
        loser_service = service_b if first_winner == "order_a" else service_a
        loser_raw = raw_b if first_winner == "order_a" else raw_a
        loser_key = key_b if first_winner == "order_a" else key_a
        retry_result = await _retry_failed_notify(
            loser_connection,
            loser_service,
            loser_raw,
            loser_key,
        )
        assert retry_result[0] == "conflict"
        assert retry_result[1] == "微信交易号已绑定其他订单"

        order_rows = await first_connection.execute_fetchall(
            "SELECT id, status, payment FROM orders WHERE id IN (?, ?) ORDER BY id",
            (order_a, order_b),
        )
        transaction_rows = await first_connection.execute_fetchall(
            "SELECT transaction_id, order_id FROM payment_transactions "
            "WHERE transaction_id = ?",
            (TRANSACTION_ID,),
        )
        event_rows = await first_connection.execute_fetchall(
            "SELECT order_id, status, operator FROM order_events "
            "WHERE order_id IN (?, ?) ORDER BY order_id, id",
            (order_a, order_b),
        )
        member_rows = await first_connection.execute_fetchall(
            "SELECT mobile, stored_value_fen, points FROM member_balance "
            "WHERE mobile IN (?, ?) ORDER BY mobile",
            (mobile_a, mobile_b),
        )
        balance_rows = await first_connection.execute_fetchall(
            "SELECT biz_id, unique_id, amount_fen FROM balance_ledger "
            "WHERE biz_id IN (?, ?) ORDER BY biz_id, id",
            (order_a, order_b),
        )
        points_rows = await first_connection.execute_fetchall(
            "SELECT biz_id, unique_id, event_type, amount, total FROM points_ledger "
            "WHERE biz_id IN (?, ?) ORDER BY biz_id, id",
            (order_a, order_b),
        )
        operation_rows = await first_connection.execute_fetchall(
            "SELECT subject_id, unique_id, operation_type FROM ledger_operation "
            "WHERE subject_id IN (?, ?) ORDER BY subject_id, id",
            (order_a, order_b),
        )
        coupon_rows = await first_connection.execute_fetchall(
            "SELECT coupon_id, status, order_no, deducted_fen FROM coupon_inventory "
            "WHERE coupon_id IN (?, ?) ORDER BY coupon_id, id",
            (coupon_a, coupon_b),
        )
        inbox_rows = await first_connection.execute_fetchall(
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key IN (?, ?) ORDER BY message_key",
            (key_a, key_b),
        )

        winner_order = order_a if first_winner == "order_a" else order_b
        loser_order = order_b if first_winner == "order_a" else order_a
        winner_coupon = coupon_a if first_winner == "order_a" else coupon_b
        loser_coupon = coupon_b if first_winner == "order_a" else coupon_a
        winner_mobile = mobile_a if first_winner == "order_a" else mobile_b
        loser_mobile = mobile_b if first_winner == "order_a" else mobile_a
        winner_key = key_a if first_winner == "order_a" else key_b
        loser_key_final = key_b if first_winner == "order_a" else key_a
        orders = {str(row["id"]): row for row in order_rows}
        assert set(orders) == {order_a, order_b}
        winner_payment = json.loads(str(orders[winner_order]["payment"]))
        loser_payment = json.loads(str(orders[loser_order]["payment"]))
        assert str(orders[winner_order]["status"]) == OrderStatus.PENDING.value
        assert str(orders[loser_order]["status"]) == OrderStatus.PENDING.value
        assert winner_payment["status"] == "paid"
        assert winner_payment["method"] == "combined"
        assert winner_payment["transactionId"] == TRANSACTION_ID
        assert int(winner_payment["couponFen"]) == COUPON_FEN
        assert int(winner_payment["balanceFen"]) == BALANCE_FEN
        assert int(winner_payment["externalPaidFen"]) == EXTERNAL_FEN
        assert int(winner_payment["pointsAwarded"]) == EXPECTED_AWARD_POINTS
        assert loser_payment["status"] == "partial"
        assert "transactionId" not in loser_payment
        assert int(loser_payment.get("pointsAwarded", 0)) == 0
        assert [dict(row) for row in transaction_rows] == [
            {"transaction_id": TRANSACTION_ID, "order_id": winner_order}
        ]
        assert [dict(row) for row in event_rows] == [
            {"order_id": winner_order, "status": "paid", "operator": "wechat-pay"}
        ]
        members = {str(row["mobile"]): dict(row) for row in member_rows}
        assert members == {
            loser_mobile: {
                "mobile": loser_mobile,
                "stored_value_fen": INITIAL_BALANCE_FEN - BALANCE_FEN,
                "points": 0,
            },
            winner_mobile: {
                "mobile": winner_mobile,
                "stored_value_fen": INITIAL_BALANCE_FEN - BALANCE_FEN,
                "points": EXPECTED_AWARD_POINTS,
            },
        }
        balances = {str(row["biz_id"]): dict(row) for row in balance_rows}
        assert balances == {
            loser_order: {
                "biz_id": loser_order,
                "unique_id": f"combined_pay:{loser_order}",
                "amount_fen": -BALANCE_FEN,
            },
            winner_order: {
                "biz_id": winner_order,
                "unique_id": f"combined_pay:{winner_order}",
                "amount_fen": -BALANCE_FEN,
            },
        }
        assert [dict(row) for row in points_rows] == [
            {
                "biz_id": winner_order,
                "unique_id": f"points:award:{winner_order}",
                "event_type": "order_award",
                "amount": EXPECTED_AWARD_POINTS,
                "total": EXPECTED_AWARD_POINTS,
            }
        ]
        assert [dict(row) for row in operation_rows] == [
            {
                "subject_id": winner_order,
                "unique_id": f"ledger:settle_award:{winner_order}",
                "operation_type": "settle_award",
            }
        ]
        coupons: dict[str, list[dict]] = {}
        for row in coupon_rows:
            coupons.setdefault(str(row["coupon_id"]), []).append(dict(row))
        assert coupons == {
            loser_coupon: [
                {
                    "coupon_id": loser_coupon,
                    "status": CouponStatus.TAKE,
                    "order_no": "",
                    "deducted_fen": 0,
                }
            ],
            winner_coupon: [
                {
                    "coupon_id": winner_coupon,
                    "status": CouponStatus.TAKE,
                    "order_no": "",
                    "deducted_fen": 0,
                },
                {
                    "coupon_id": winner_coupon,
                    "status": CouponStatus.CONSUME,
                    "order_no": winner_order,
                    "deducted_fen": COUPON_FEN,
                },
            ],
        }
        inbox = {str(row["message_key"]): dict(row) for row in inbox_rows}
        assert inbox == {
            loser_key_final: {
                "message_key": loser_key_final,
                "status": "failed",
                "attempt_count": 2,
            },
            winner_key: {
                "message_key": winner_key,
                "status": "processed",
                "attempt_count": 1,
            },
        }
    finally:
        await close_db(second_connection)
        await close_db(first_connection)
