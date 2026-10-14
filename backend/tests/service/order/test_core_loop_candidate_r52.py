"""MiniApp 核心闭环 r52：同一订单两笔部分退款并发累计复核。"""

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

ORDER_ID = "order_concurrent_partial_refunds_r52_001"
USER_ID = "wx_concurrent_partial_refunds_r52_001"
OPENID = "concurrent_partial_refunds_r52_001"
MOBILE = "13800003052"
ORDER_AMOUNT_FEN = 12_000
BALANCE_FEN = 2_000
EXTERNAL_FEN = 10_000
REFUND_FEN = 6_000
TOTAL_REFUND_FEN = REFUND_FEN * 2
INITIAL_BALANCE_FEN = 20_000
EXPECTED_AWARD_POINTS = EXTERNAL_FEN // 100
TRANSACTION_ID = "4200000000202609251234567952"
MCH_ID = "mch-concurrent-partial-refunds-r52"
APP_ID = "appid-concurrent-partial-refunds-r52"
REFUND_A = "R-concurrent-partial-refunds-r52-a"
REFUND_B = "R-concurrent-partial-refunds-r52-b"
EVENT_A = "EV-concurrent-partial-refunds-r52-a"
EVENT_B = "EV-concurrent-partial-refunds-r52-b"
KEY_A = f"wechat_pay_notify:{EVENT_A}"
KEY_B = f"wechat_pay_notify:{EVENT_B}"


class _LocalWechatPay:
    """为组合支付和支付查询提供不触网的本地微信集成。"""

    def is_ready(self) -> bool:
        return False

    def format_success_time(self, value: str) -> str:
        return "2026-09-25 15:00:00"


def _build_runtime_service(handle: DatabaseHandle) -> OrderPaymentRuntimeService:
    """构建真实支付查询与退款通知入口。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=_LocalWechatPay(),
    )


def _build_combined_service(handle: DatabaseHandle) -> StoredValueOrderPaymentService:
    """构建真实储值余额组合支付服务。"""
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )
    return StoredValueOrderPaymentService(
        order_repo=OrderRepo(handle),
        member_service=member_service,
        wechat_pay_service=_LocalWechatPay(),
    )


def _payment_query() -> dict:
    """构造组合支付外部腿支付成功查询。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": MCH_ID,
        "appid": APP_ID,
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T15:00:00+08:00",
    }


def _refund_transaction(out_refund_no: str) -> dict:
    """构造同一原支付交易下的 6,000 分退款成功事实。"""
    return {
        "mchid": MCH_ID,
        "out_trade_no": ORDER_ID,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": out_refund_no,
        "refund_id": f"wx-{out_refund_no}",
        "refund_status": "SUCCESS",
        "success_time": "2026-09-25T15:05:00+08:00",
        "amount": {
            "total": EXTERNAL_FEN,
            "refund": REFUND_FEN,
            "payer_total": EXTERNAL_FEN,
            "payer_refund": REFUND_FEN,
        },
    }


def _notify_body(event_id: str, out_refund_no: str) -> bytes:
    """构造携带独立事件标识和退款单号的本地通知外层载荷。"""
    return json.dumps(
        {
            "id": event_id,
            "event_type": "REFUND.SUCCESS",
            "resource": {
                "kind": "refund",
                "order_id": ORDER_ID,
                "out_refund_no": out_refund_no,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")


async def _seed_and_pay_order(
    connection: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """建立会员、组合支付订单，并完成真实余额扣减和微信腿入账。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, ?, 'high', 1)",
        (f"cm_{ORDER_ID}", MOBILE, "并发部分退款复核会员"),
    )
    await connection.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (
            f"cil_{ORDER_ID}",
            f"cm_{ORDER_ID}",
            OPENID,
            OPENID,
        ),
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
                build_initial_payment("2026-09-25 14:00:00"),
                ensure_ascii=False,
            ),
            status=OrderStatus.PENDING,
            created_at="2026-09-25 14:00:00",
            updated_at="2026-09-25 14:00:00",
        )
    )
    await connection.commit()

    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
    handle = DatabaseHandle(connection)
    combined = await _build_combined_service(handle).prepare_combined_payment(
        ORDER_ID,
        user_id=USER_ID,
        balance_fen=BALANCE_FEN,
    )
    assert combined["payment"]["status"] == "partial"
    assert int(combined["payment"]["remainFen"]) == EXTERNAL_FEN
    paid = await _build_runtime_service(handle).reconcile_pay_from_query(
        _payment_query()
    )
    assert paid["paymentStatus"] == "paid"


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


async def _retry_failed_refunds(
    connection: aiosqlite.Connection,
    services: dict[str, OrderPaymentRuntimeService],
    raw_bodies: dict[str, bytes],
) -> None:
    """按生产 inbox 路径重投所有瞬时锁失败的退款通知。"""
    failed_rows = await connection.execute_fetchall(
        "SELECT message_key FROM inbox_events "
        "WHERE message_key IN (?, ?) AND status = 'failed'",
        (KEY_A, KEY_B),
    )
    for row in failed_rows:
        message_key = str(row["message_key"])
        await connection.execute(
            "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
            "WHERE message_key = ?",
            (message_key,),
        )
    await connection.commit()
    for row in failed_rows:
        message_key = str(row["message_key"])
        result = await _attempt_refund(services[message_key], raw_bodies[message_key])
        assert result[0] == "ok"
        assert isinstance(result[1], dict)
        assert result[1]["kind"] == "rejected_recorded"


async def _read_final_state(
    connection: aiosqlite.Connection,
) -> dict[str, list[dict]]:
    """读取订单、交易、退款、资产、案件和 inbox 最终事实。"""
    queries = {
        "orders": (
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        ),
        "transactions": (
            "SELECT transaction_id, order_id FROM payment_transactions "
            "WHERE transaction_id = ?",
            (TRANSACTION_ID,),
        ),
        "refunds": (
            "SELECT out_refund_no, order_id, transaction_id, payer_refund_fen, "
            "source FROM wechat_refund_events WHERE order_id = ? "
            "ORDER BY out_refund_no",
            (ORDER_ID,),
        ),
        "members": (
            "SELECT stored_value_fen, points FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        ),
        "balance_ledger": (
            "SELECT unique_id, amount_fen, balance_after_fen FROM balance_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "points_ledger": (
            "SELECT unique_id, event_type, amount, total FROM points_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "ledger_operations": (
            "SELECT unique_id, operation_type FROM ledger_operation "
            "WHERE subject_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "refund_operations": (
            "SELECT operation_key, status, clawback_amount FROM refund_operation "
            "WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "cases": (
            "SELECT unique_id, reason, amount, status FROM points_refund_reconcile "
            "WHERE order_id = ? ORDER BY unique_id",
            (ORDER_ID,),
        ),
        "inbox": (
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key IN (?, ?) ORDER BY message_key",
            (KEY_A, KEY_B),
        ),
    }
    return {
        name: await connection.execute_fetchall(sql, parameters)
        for name, (sql, parameters) in queries.items()
    }


def _assert_final_state(
    state: dict[str, list[dict]],
    first_winner: str,
) -> None:
    """断言两笔部分退款最终只确认第一笔并完整记录超额事实。"""
    assert len(state["orders"]) == 1
    assert str(state["orders"][0]["status"]) == OrderStatus.PENDING.value
    payment = json.loads(str(state["orders"][0]["payment"]))
    assert payment["status"] == "paid"
    assert payment["method"] == "combined"
    assert payment["transactionId"] == TRANSACTION_ID
    assert int(payment["balanceFen"]) == BALANCE_FEN
    assert int(payment["externalPaidFen"]) == EXTERNAL_FEN
    assert int(payment["pointsAwarded"]) == EXPECTED_AWARD_POINTS
    assert payment["refundStatus"] == "over"
    assert int(payment["refundFen"]) == TOTAL_REFUND_FEN

    assert [dict(row) for row in state["transactions"]] == [
        {"transaction_id": TRANSACTION_ID, "order_id": ORDER_ID}
    ]
    assert [dict(row) for row in state["refunds"]] == [
        {
            "out_refund_no": REFUND_A,
            "order_id": ORDER_ID,
            "transaction_id": TRANSACTION_ID,
            "payer_refund_fen": REFUND_FEN,
            "source": "notify",
        },
        {
            "out_refund_no": REFUND_B,
            "order_id": ORDER_ID,
            "transaction_id": TRANSACTION_ID,
            "payer_refund_fen": REFUND_FEN,
            "source": "notify",
        },
    ]

    assert [dict(row) for row in state["members"]] == [
        {
            "stored_value_fen": INITIAL_BALANCE_FEN - BALANCE_FEN,
            "points": EXPECTED_AWARD_POINTS,
        }
    ]
    assert [dict(row) for row in state["balance_ledger"]] == [
        {
            "unique_id": f"combined_pay:{ORDER_ID}",
            "amount_fen": -BALANCE_FEN,
            "balance_after_fen": INITIAL_BALANCE_FEN - BALANCE_FEN,
        }
    ]
    assert [dict(row) for row in state["points_ledger"]] == [
        {
            "unique_id": f"points:award:{ORDER_ID}",
            "event_type": "order_award",
            "amount": EXPECTED_AWARD_POINTS,
            "total": EXPECTED_AWARD_POINTS,
        }
    ]
    assert [dict(row) for row in state["ledger_operations"]] == [
        {
            "unique_id": f"ledger:settle_award:{ORDER_ID}",
            "operation_type": "settle_award",
        }
    ]
    assert state["refund_operations"] == []

    first_refund = REFUND_A if first_winner == "refund_a" else REFUND_B
    second_refund = REFUND_B if first_winner == "refund_a" else REFUND_A
    assert {str(row["unique_id"]) for row in state["cases"]} == {
        f"refund:partial:{first_refund}",
        f"refund:over_refund:{second_refund}",
    }

    inbox = {str(row["message_key"]): dict(row) for row in state["inbox"]}
    assert set(inbox) == {KEY_A, KEY_B}
    assert all(str(row["status"]) == "processed" for row in inbox.values())
    assert all(1 <= int(row["attempt_count"]) <= 2 for row in inbox.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["refund_a", "refund_b"])
async def test_concurrent_partial_refunds_record_over_refund_without_compensation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    first_winner: str,
) -> None:
    """同一订单两笔部分退款并发后必须收敛为超额退款且不补偿资产。"""
    database_path = tmp_path / f"concurrent-partial-refunds-{first_winner}-r52.db"
    first_connection = await init_db(str(database_path))
    second_connection = await init_db(str(database_path))
    first_handle = DatabaseHandle(first_connection)
    second_handle = DatabaseHandle(second_connection)
    try:
        await _seed_and_pay_order(first_connection, monkeypatch)
        service_a = _build_runtime_service(first_handle)
        service_b = _build_runtime_service(second_handle)
        raw_a = _notify_body(EVENT_A, REFUND_A)
        raw_b = _notify_body(EVENT_B, REFUND_B)
        services = {KEY_A: service_a, KEY_B: service_b}
        raw_bodies = {KEY_A: raw_a, KEY_B: raw_b}

        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_verify_wechat_notify_signature",
            lambda self, raw_body, headers: True,
        )
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_decrypt_wechat_resource",
            lambda self, resource: _refund_transaction(str(resource["out_refund_no"])),
        )

        all_claims_committed = asyncio.Event()
        claim_committed = {
            id(first_handle): asyncio.Event(),
            id(second_handle): asyncio.Event(),
        }
        original_claim_notify = notify_intake.claim_notify
        original_get_order = OrderRepo.get_order

        async def commit_claims_before_business(
            db,
            event_id: str,
            payload: dict | None = None,
            *,
            lease_seconds: int = notify_intake.DEFAULT_NOTIFY_LEASE_SECONDS,
        ) -> dict:
            """先提交两个 inbox claim，再让两笔退款竞争业务事务。"""
            claim = await original_claim_notify(
                db,
                event_id,
                payload,
                lease_seconds=lease_seconds,
            )
            await db.commit()
            claim_committed[id(db)].set()
            if all(event.is_set() for event in claim_committed.values()):
                all_claims_committed.set()
            await asyncio.wait_for(all_claims_committed.wait(), timeout=5)
            return claim

        both_snapshots_read = asyncio.Barrier(2)
        winner_committed = asyncio.Event()
        observed_handles: set[int] = set()
        first_handle_key = id(first_handle)
        second_handle_key = id(second_handle)

        async def read_same_paid_snapshot_before_refund(
            repo: OrderRepo,
            order_id: str,
        ):
            """让两笔退款读取同一已支付快照，再按参数固定首胜顺序。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if (
                order_id == ORDER_ID
                and handle_key in {first_handle_key, second_handle_key}
                and handle_key not in observed_handles
            ):
                observed_handles.add(handle_key)
                await asyncio.wait_for(both_snapshots_read.wait(), timeout=5)
                role = "refund_a" if handle_key == first_handle_key else "refund_b"
                if role != first_winner:
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(
            notify_intake, "claim_notify", commit_claims_before_business
        )
        monkeypatch.setattr(
            OrderRepo,
            "get_order",
            read_same_paid_snapshot_before_refund,
        )

        async def run_a() -> tuple[str, dict | str]:
            result = await _attempt_refund(service_a, raw_a)
            if first_winner == "refund_a":
                winner_committed.set()
            return result

        async def run_b() -> tuple[str, dict | str]:
            result = await _attempt_refund(service_b, raw_b)
            if first_winner == "refund_b":
                winner_committed.set()
            return result

        result_a, result_b = await asyncio.gather(run_a(), run_b())
        winner_result = result_a if first_winner == "refund_a" else result_b
        loser_result = result_b if first_winner == "refund_a" else result_a
        assert winner_result[0] == "ok"
        assert isinstance(winner_result[1], dict)
        assert winner_result[1]["kind"] == "acknowledged"
        assert winner_result[1]["accumulatedFen"] == REFUND_FEN
        assert loser_result[0] in {"locked", "ok"}
        if loser_result[0] == "ok":
            assert isinstance(loser_result[1], dict)
            assert loser_result[1]["kind"] == "rejected_recorded"
        assert observed_handles == {first_handle_key, second_handle_key}

        monkeypatch.setattr(notify_intake, "claim_notify", original_claim_notify)
        monkeypatch.setattr(OrderRepo, "get_order", original_get_order)
        await _retry_failed_refunds(first_connection, services, raw_bodies)

        duplicate_a = await _attempt_refund(service_a, raw_a)
        await first_handle.commit()
        duplicate_b = await _attempt_refund(service_b, raw_b)
        assert duplicate_a == ("ok", {"duplicate": True, "kind": "duplicate"})
        assert duplicate_b == ("ok", {"duplicate": True, "kind": "duplicate"})

        state = await _read_final_state(first_connection)
        _assert_final_state(state, first_winner)
    finally:
        await close_db(second_connection)
        await close_db(first_connection)
