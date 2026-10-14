"""MiniApp 核心闭环 r50：退款先到时跨订单共享微信交易号候选复核。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.models.order import Order, OrderStatus
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.base import DatabaseHandle
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_repo import OrderRepo
from app.service.order import notify_intake
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
)

TRANSACTION_ID = "4200000000202609251234567950"
ORDER_AMOUNT_FEN = 10_000
BALANCE_FEN = 2_000
EXTERNAL_FEN = ORDER_AMOUNT_FEN - BALANCE_FEN
INITIAL_BALANCE_FEN = 20_000
MCH_ID = "mch-cross-order-refund-r50"


class _LocalWechatPay:
    """为组合支付测试提供不触网的微信降级会话。"""

    def is_ready(self) -> bool:
        return False

    def format_success_time(self, value: str) -> str:
        return "2026-09-25 15:00:00"


def _member_service(handle: DatabaseHandle) -> MemberBalanceService:
    """构建真实会员余额服务。"""
    return MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )


def _runtime_service(handle: DatabaseHandle) -> OrderPaymentRuntimeService:
    """构建真实退款通知入口。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=_LocalWechatPay(),
    )


def _refund_transaction(order_id: str, out_refund_no: str) -> dict:
    """构造两个订单共享原支付交易号的退款成功事务体。"""
    return {
        "mchid": MCH_ID,
        "out_trade_no": order_id,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": out_refund_no,
        "refund_id": f"wx-{out_refund_no}",
        "refund_status": "SUCCESS",
        "success_time": "2026-09-25T15:05:00+08:00",
        "amount": {
            "total": EXTERNAL_FEN,
            "refund": EXTERNAL_FEN,
            "payer_total": EXTERNAL_FEN,
            "payer_refund": EXTERNAL_FEN,
        },
    }


def _notify_body(event_id: str, order_id: str, out_refund_no: str) -> bytes:
    """构造携带独立事件标识和退款事实的本地通知外层载荷。"""
    return json.dumps(
        {
            "id": event_id,
            "event_type": "REFUND.SUCCESS",
            "resource": {
                "kind": "refund",
                "order_id": order_id,
                "out_refund_no": out_refund_no,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")


async def _seed_partial_order(
    connection: aiosqlite.Connection,
    *,
    suffix: str,
    mobile: str,
    user_id: str,
    order_id: str,
) -> None:
    """写入一套独立会员和已扣储值余额腿的组合支付订单。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, ?, 'high', 1)",
        (f"cm_{suffix}", mobile, f"跨订单退款会员{suffix}"),
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
                build_initial_payment("2026-09-25 14:00:00"),
                ensure_ascii=False,
            ),
            status=OrderStatus.PENDING,
            created_at="2026-09-25 14:00:00",
            updated_at="2026-09-25 14:00:00",
        )
    )
    await connection.commit()

    handle = DatabaseHandle(connection)
    combined_service = StoredValueOrderPaymentService(
        order_repo=OrderRepo(handle),
        member_service=_member_service(handle),
        wechat_pay_service=_LocalWechatPay(),
    )
    result = await combined_service.prepare_combined_payment(
        order_id,
        user_id=user_id,
        balance_fen=BALANCE_FEN,
    )
    assert result["payment"]["status"] == "partial"
    await connection.commit()


async def _attempt_refund(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, dict | str]:
    """执行退款通知入口并区分业务冲突与 SQLite 瞬时锁冲突。"""
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


async def _retry_failed_refund(
    connection: aiosqlite.Connection,
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
    message_key: str,
) -> tuple[str, dict | str]:
    """按生产 inbox 路径重投跨订单退款交易号冲突。"""
    await connection.execute(
        "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
        "WHERE message_key = ? AND status = 'failed'",
        (message_key,),
    )
    await connection.commit()
    return await _attempt_refund(service, raw_body)


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["order_a", "order_b"])
async def test_same_transaction_refund_cannot_compensate_two_orders(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    first_winner: str,
) -> None:
    """同一微信原支付交易号的退款只能补偿一个订单。"""
    database_path = tmp_path / f"cross-order-refund-{first_winner}-r50.db"
    first_connection = await init_db(str(database_path))
    second_connection = await init_db(str(database_path))
    first_handle = DatabaseHandle(first_connection)
    second_handle = DatabaseHandle(second_connection)
    order_a = "order_cross_refund_r50_a"
    order_b = "order_cross_refund_r50_b"
    user_a = "wx_cross_refund_r50_a"
    user_b = "wx_cross_refund_r50_b"
    mobile_a = "13800003051"
    mobile_b = "13800003052"
    refund_a = "R-cross-refund-r50-a"
    refund_b = "R-cross-refund-r50-b"
    event_a = "EV-cross-refund-r50-a"
    event_b = "EV-cross-refund-r50-b"
    key_a = f"wechat_pay_notify:{event_a}"
    key_b = f"wechat_pay_notify:{event_b}"
    try:
        await _seed_partial_order(
            first_connection,
            suffix="cross_refund_r50_a",
            mobile=mobile_a,
            user_id=user_a,
            order_id=order_a,
        )
        await _seed_partial_order(
            first_connection,
            suffix="cross_refund_r50_b",
            mobile=mobile_b,
            user_id=user_b,
            order_id=order_b,
        )
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_verify_wechat_notify_signature",
            lambda self, raw_body, headers: True,
        )
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_decrypt_wechat_resource",
            lambda self, resource: _refund_transaction(
                str(resource["order_id"]),
                str(resource["out_refund_no"]),
            ),
        )
        raw_a = _notify_body(event_a, order_a, refund_a)
        raw_b = _notify_body(event_b, order_b, refund_b)
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
            """先提交两个 inbox claim，再让两个退款事务读取旧订单快照。"""
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

        async def read_old_snapshots_before_refund(
            repo: OrderRepo,
            order_id: str,
        ):
            """让两个退款先读各自旧快照，再按参数固定首胜顺序。"""
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

        monkeypatch.setattr(
            OrderRepo,
            "get_order",
            read_old_snapshots_before_refund,
        )

        async def run_a() -> tuple[str, dict | str]:
            result = await _attempt_refund(service_a, raw_a)
            if first_winner == "order_a":
                winner_committed.set()
            return result

        async def run_b() -> tuple[str, dict | str]:
            result = await _attempt_refund(service_b, raw_b)
            if first_winner == "order_b":
                winner_committed.set()
            return result

        result_a, result_b = await asyncio.gather(run_a(), run_b())
        winner_result = result_a if first_winner == "order_a" else result_b
        loser_result = result_b if first_winner == "order_a" else result_a
        assert winner_result[0] == "ok"
        assert loser_result[0] in {"locked", "ok", "conflict"}
        assert observed_handles == {first_handle_key, second_handle_key}

        loser_connection = (
            second_connection if first_winner == "order_a" else first_connection
        )
        loser_service = service_b if first_winner == "order_a" else service_a
        loser_raw = raw_b if first_winner == "order_a" else raw_a
        loser_key = key_b if first_winner == "order_a" else key_a
        retry_result = await _retry_failed_refund(
            loser_connection,
            loser_service,
            loser_raw,
            loser_key,
        )
        if retry_result[0] == "ok" and isinstance(retry_result[1], dict):
            if retry_result[1].get("status") == "failed":
                retry_result = await _attempt_refund(loser_service, loser_raw)
        assert retry_result[0] == "ok"
        assert isinstance(retry_result[1], dict)
        assert retry_result[1]["kind"] == "rejected_recorded"
        assert "交易号已绑定其他订单" in str(retry_result[1]["rejected"])

        order_rows = await first_connection.execute_fetchall(
            "SELECT id, status, payment FROM orders WHERE id IN (?, ?) ORDER BY id",
            (order_a, order_b),
        )
        transaction_rows = await first_connection.execute_fetchall(
            "SELECT transaction_id, order_id FROM payment_transactions "
            "WHERE transaction_id = ?",
            (TRANSACTION_ID,),
        )
        refund_rows = await first_connection.execute_fetchall(
            "SELECT out_refund_no, order_id, transaction_id, payer_refund_fen "
            "FROM wechat_refund_events ORDER BY out_refund_no"
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
        case_rows = await first_connection.execute_fetchall(
            "SELECT order_id, reason, amount, status FROM points_refund_reconcile "
            "ORDER BY order_id, id"
        )
        inbox_rows = await first_connection.execute_fetchall(
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key IN (?, ?) ORDER BY message_key",
            (key_a, key_b),
        )

        winner_order = order_a if first_winner == "order_a" else order_b
        loser_order = order_b if first_winner == "order_a" else order_a
        winner_mobile = mobile_a if first_winner == "order_a" else mobile_b
        loser_mobile = mobile_b if first_winner == "order_a" else mobile_a
        orders = {str(row["id"]): row for row in order_rows}
        winner_payment = json.loads(str(orders[winner_order]["payment"]))
        loser_payment = json.loads(str(orders[loser_order]["payment"]))
        assert str(orders[winner_order]["status"]) == OrderStatus.PENDING.value
        assert str(orders[loser_order]["status"]) == OrderStatus.PENDING.value
        assert winner_payment["status"] == "partial"
        assert winner_payment["refundStatus"] == "full"
        assert int(winner_payment["refundFen"]) == EXTERNAL_FEN
        assert loser_payment["status"] == "partial"
        assert "refundStatus" not in loser_payment
        assert [dict(row) for row in transaction_rows] == [
            {"transaction_id": TRANSACTION_ID, "order_id": winner_order}
        ]
        assert [dict(row) for row in refund_rows] == [
            {
                "out_refund_no": refund_a if winner_order == order_a else refund_b,
                "order_id": winner_order,
                "transaction_id": TRANSACTION_ID,
                "payer_refund_fen": EXTERNAL_FEN,
            }
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
                "stored_value_fen": INITIAL_BALANCE_FEN,
                "points": 0,
            },
        }
        balances: dict[str, list[dict]] = {}
        for row in balance_rows:
            balances.setdefault(str(row["biz_id"]), []).append(dict(row))
        assert balances[winner_order] == [
            {
                "biz_id": winner_order,
                "unique_id": f"combined_pay:{winner_order}",
                "amount_fen": -BALANCE_FEN,
            },
            {
                "biz_id": winner_order,
                "unique_id": f"order_refund:{winner_order}",
                "amount_fen": BALANCE_FEN,
            },
        ]
        assert balances[loser_order] == [
            {
                "biz_id": loser_order,
                "unique_id": f"combined_pay:{loser_order}",
                "amount_fen": -BALANCE_FEN,
            }
        ]
        assert [dict(row) for row in case_rows] == [
            {
                "order_id": loser_order,
                "reason": f"refund:transaction_bound:{TRANSACTION_ID}",
                "amount": EXTERNAL_FEN,
                "status": "open",
            }
        ]
        inbox = {str(row["message_key"]): dict(row) for row in inbox_rows}
        assert all(str(row["status"]) == "processed" for row in inbox.values())
    finally:
        await close_db(second_connection)
        await close_db(first_connection)
