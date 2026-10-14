"""MiniApp 核心闭环 r44：支付查询恢复与退款通知并发候选复核。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.config import settings
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
from app.service.integrations.wechat_pay import WechatPayPrepayResult
from app.service.order import notify_intake
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
)

ORDER_ID = "order_pay_query_refund_notify_race_r44_001"
OPENID = "pay_query_refund_notify_race_r44_001"
USER_ID = f"wx_{OPENID}"
MOBILE = "13800003044"
COUPON_ID = "coupon_pay_query_refund_notify_race_r44_001"
TEMPLATE_ID = "cg_pay_query_refund_notify_race_r44_001"
ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 1_000
BALANCE_FEN = 2_000
EXTERNAL_FEN = ORDER_AMOUNT_FEN - COUPON_FEN - BALANCE_FEN
INITIAL_BALANCE_FEN = 20_000
EXPECTED_AWARD_POINTS = EXTERNAL_FEN // 100
TRANSACTION_ID = "4200000000202609251234567944"
EVENT_ID = "EV-pay-query-refund-notify-race-r44-001"
OUT_REFUND_NO = "R-pay-query-refund-notify-race-r44-001"
REFUND_ID = "refund-pay-query-refund-notify-race-r44-001"
PAYMENT_KEY = f"wechat_pay_notify:query:pay:{ORDER_ID}:{TRANSACTION_ID}"
REFUND_KEY = f"wechat_pay_notify:{EVENT_ID}"


class _LocalWechatPay:
    """为组合预下单、支付查询和退款通知提供不触网的本地支付集成。"""

    def is_ready(self) -> bool:
        return True

    async def create_jsapi_prepay(
        self,
        *,
        order_id: str,
        total_fen: int,
        description: str,
        payer_openid: str,
    ) -> WechatPayPrepayResult:
        return WechatPayPrepayResult(
            prepay_id=f"prepay-{order_id}-{total_fen}",
            appid="appid-pay-query-refund-race-r44",
        )

    def build_payment_params(
        self,
        prepay_id: str,
        *,
        signer,
    ) -> dict:
        return {
            "timeStamp": "1789756800",
            "nonceStr": "nonce-r44",
            "package": f"prepay_id={prepay_id}",
            "signType": "RSA",
            "paySign": signer(f"prepay:{prepay_id}"),
        }

    def sign_with_rsa(self, message: str) -> str:
        return f"signature:{message}"

    def format_success_time(self, value: str) -> str:
        return "2026-09-25 12:00:00"


def _build_member_service(handle: DatabaseHandle) -> MemberBalanceService:
    """构建真实会员余额服务。"""
    return MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )


def _build_combined_service(handle: DatabaseHandle) -> StoredValueOrderPaymentService:
    """构建真实组合支付服务。"""
    return StoredValueOrderPaymentService(
        order_repo=OrderRepo(handle),
        member_service=_build_member_service(handle),
        wechat_pay_service=_LocalWechatPay(),
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


def _build_runtime_service(handle: DatabaseHandle) -> OrderPaymentRuntimeService:
    """构建真实支付查询与退款通知入口。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=_LocalWechatPay(),
        event_repo=OrderEventRepo(handle),
    )


def _payment_transaction() -> dict:
    """构造微信外部尾款支付成功查询结果。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": "mch-pay-query-refund-race-r44",
        "appid": "appid-pay-query-refund-race-r44",
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T12:00:00+08:00",
    }


def _refund_transaction() -> dict:
    """构造与外部尾款完全匹配的全额退款成功事实。"""
    return {
        "mchid": "mch-pay-query-refund-race-r44",
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
    """构造退款通知外层载荷。"""
    return json.dumps(
        {
            "id": EVENT_ID,
            "event_type": "REFUND.SUCCESS",
            "resource": {"kind": "refund"},
        },
        ensure_ascii=False,
    ).encode("utf-8")


async def _seed_order_member_and_coupon(connection: aiosqlite.Connection) -> None:
    """写入待支付订单、会员身份、足额余额和一张可用券。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '支付查询退款通知竞态会员', 'high', 1)",
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
                        "product_id": "p_pay_query_refund_r44",
                        "title": "支付查询退款通知竞态蛋糕",
                        "price_fen": ORDER_AMOUNT_FEN,
                        "quantity": 1,
                        "inventory_reserved": False,
                    }
                ],
                ensure_ascii=False,
            ),
            ORDER_AMOUNT_FEN / 100,
            json.dumps(
                build_initial_payment("2026-09-25 11:00:00"),
                ensure_ascii=False,
            ),
            "2026-09-25 11:00:00",
            "2026-09-25 11:00:00",
        ),
    )
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=TEMPLATE_ID,
            name="支付查询退款通知竞态测试券",
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
            title="支付查询退款通知竞态测试券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id=TEMPLATE_ID,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()


async def _prepare_combined_partial(connection: aiosqlite.Connection) -> None:
    """用真实券和余额服务构造待微信尾款支付的组合快照。"""
    handle = DatabaseHandle(connection)
    coupon_result = await _build_coupon_service(handle).apply_coupon(
        ORDER_ID,
        user_id=USER_ID,
        coupon_id=COUPON_ID,
    )
    assert coupon_result["paymentStatus"] == "partial"
    await connection.commit()
    combined_result = await _build_combined_service(handle).prepare_combined_payment(
        ORDER_ID,
        user_id=USER_ID,
        balance_fen=BALANCE_FEN,
    )
    assert combined_result["payment"]["status"] == "partial"
    await connection.commit()


async def _attempt_payment_query(
    service: OrderPaymentRuntimeService,
) -> tuple[str, dict | str]:
    """执行支付查询恢复并区分业务冲突与瞬时锁冲突。"""
    try:
        result = await service.reconcile_pay_from_query(_payment_transaction())
        return "ok", result
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_refund_notify(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, dict | str]:
    """执行退款通知并区分业务冲突与瞬时锁冲突。"""
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


async def _read_final_state(
    connection: aiosqlite.Connection,
) -> dict[str, list[dict]]:
    """读取订单、交易、退款、资产、异常和 inbox 最终事实。"""
    queries = {
        "orders": (
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        ),
        "transactions": (
            "SELECT order_id FROM payment_transactions "
            "WHERE transaction_id = ? ORDER BY order_id",
            (TRANSACTION_ID,),
        ),
        "refunds": (
            "SELECT out_refund_no, order_id, transaction_id, payer_refund_fen, "
            "source FROM wechat_refund_events WHERE order_id = ? "
            "ORDER BY out_refund_no",
            (ORDER_ID,),
        ),
        "events": (
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "inbox": (
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key IN (?, ?) ORDER BY message_key",
            (PAYMENT_KEY, REFUND_KEY),
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
        "reconciles": (
            "SELECT unique_id FROM points_refund_reconcile WHERE order_id = ? "
            "ORDER BY id",
            (ORDER_ID,),
        ),
        "shortfalls": (
            "SELECT operation_key FROM refund_shortfall_debt WHERE order_id = ? "
            "ORDER BY id",
            (ORDER_ID,),
        ),
        "coupons": (
            "SELECT coupon_id, status, order_no, deducted_fen "
            "FROM coupon_inventory WHERE coupon_id = ? ORDER BY id",
            (COUPON_ID,),
        ),
    }
    return {
        name: await connection.execute_fetchall(sql, parameters)
        for name, (sql, parameters) in queries.items()
    }


def _assert_common_final_state(
    state: dict[str, list[dict]],
    first_winner: str,
) -> None:
    """断言两种顺序共同的支付、退款和资产补偿事实。"""
    assert len(state["orders"]) == 1
    assert str(state["orders"][0]["status"]) == "pending"
    payment = json.loads(str(state["orders"][0]["payment"]))
    assert payment["status"] == "paid"
    assert payment["method"] == "combined"
    assert payment["transactionId"] == TRANSACTION_ID
    assert int(payment["couponFen"]) == COUPON_FEN
    assert int(payment["balanceFen"]) == BALANCE_FEN
    assert int(payment["externalPaidFen"]) == EXTERNAL_FEN
    assert int(payment.get("pointsAwarded", 0)) == 0
    assert payment["refundStatus"] == "full"
    assert int(payment["refundFen"]) == EXTERNAL_FEN
    assert [dict(row) for row in state["transactions"]] == [{"order_id": ORDER_ID}]
    assert [dict(row) for row in state["refunds"]] == [
        {
            "out_refund_no": OUT_REFUND_NO,
            "order_id": ORDER_ID,
            "transaction_id": TRANSACTION_ID,
            "payer_refund_fen": EXTERNAL_FEN,
            "source": "notify",
        }
    ]
    assert [dict(row) for row in state["events"]] == [
        {"status": "paid", "operator": "wechat-pay"}
    ]
    assert [dict(row) for row in state["members"]] == [
        {"stored_value_fen": INITIAL_BALANCE_FEN, "points": 0}
    ]
    assert [dict(row) for row in state["balance_ledger"]] == [
        {
            "unique_id": f"combined_pay:{ORDER_ID}",
            "amount_fen": -BALANCE_FEN,
            "balance_after_fen": INITIAL_BALANCE_FEN - BALANCE_FEN,
        },
        {
            "unique_id": f"order_refund:{ORDER_ID}",
            "amount_fen": BALANCE_FEN,
            "balance_after_fen": INITIAL_BALANCE_FEN,
        },
    ]
    assert state["reconciles"] == []
    assert state["shortfalls"] == []
    assert {
        str(row["message_key"]): (str(row["status"]), int(row["attempt_count"]))
        for row in state["inbox"]
    } == {
        PAYMENT_KEY: ("processed", 1 if first_winner == "payment" else 2),
        REFUND_KEY: ("processed", 1 if first_winner == "refund" else 2),
    }


def _assert_payment_first_assets(state: dict[str, list[dict]]) -> None:
    """断言支付先提交时券、积分均只结算一次并完整退回。"""
    assert [dict(row) for row in state["points_ledger"]] == [
        {
            "unique_id": f"points:award:{ORDER_ID}",
            "event_type": "order_award",
            "amount": EXPECTED_AWARD_POINTS,
            "total": EXPECTED_AWARD_POINTS,
        },
        {
            "unique_id": f"points:refund:{ORDER_ID}:clawback",
            "event_type": "order_refund",
            "amount": -EXPECTED_AWARD_POINTS,
            "total": 0,
        },
    ]
    assert [dict(row) for row in state["ledger_operations"]] == [
        {
            "unique_id": f"ledger:settle_award:{ORDER_ID}",
            "operation_type": "settle_award",
        },
        {
            "unique_id": f"ledger:refund_clawback:{ORDER_ID}",
            "operation_type": "refund_clawback",
        },
    ]
    assert [dict(row) for row in state["refund_operations"]] == [
        {
            "operation_key": f"points:refund:{ORDER_ID}",
            "status": "succeeded",
            "clawback_amount": EXPECTED_AWARD_POINTS,
        }
    ]
    assert [dict(row) for row in state["coupons"]] == [
        {
            "coupon_id": COUPON_ID,
            "status": CouponStatus.TAKE,
            "order_no": "",
            "deducted_fen": 0,
        },
        {
            "coupon_id": COUPON_ID,
            "status": CouponStatus.CONSUME,
            "order_no": ORDER_ID,
            "deducted_fen": COUPON_FEN,
        },
        {
            "coupon_id": COUPON_ID,
            "status": CouponStatus.BACK,
            "order_no": ORDER_ID,
            "deducted_fen": COUPON_FEN,
        },
        # r78（`M-20260926-028`）：退款腿除 BACK 冲正外还在新周期补写 TAKE，
        # 把可持有性还给客户——全额退款必须同时退掉现金与券，券要能再次使用。
        {
            "coupon_id": COUPON_ID,
            "status": CouponStatus.TAKE,
            "order_no": ORDER_ID,
            "deducted_fen": 0,
        },
    ]


def _assert_refund_first_assets(state: dict[str, list[dict]]) -> None:
    """断言退款先提交时不得再核销券或发放积分。"""
    assert state["points_ledger"] == []
    assert state["ledger_operations"] == []
    assert state["refund_operations"] == []
    assert [dict(row) for row in state["coupons"]] == [
        {
            "coupon_id": COUPON_ID,
            "status": CouponStatus.TAKE,
            "order_no": "",
            "deducted_fen": 0,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["payment", "refund"])
async def test_payment_query_and_refund_notify_race_preserves_single_settlement(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    first_winner: str,
) -> None:
    """两种提交顺序都只能形成一次支付、退款和资产补偿事实。"""
    database_path = tmp_path / f"pay-query-refund-notify-race-{first_winner}-r44.db"
    payment_connection = await init_db(str(database_path))
    refund_connection = await init_db(str(database_path))
    payment_handle = DatabaseHandle(payment_connection)
    refund_handle = DatabaseHandle(refund_connection)
    try:
        await _seed_order_member_and_coupon(payment_connection)
        await _prepare_combined_partial(payment_connection)
        payment_service = _build_runtime_service(payment_handle)
        refund_service = _build_runtime_service(refund_handle)
        monkeypatch.setattr(
            settings, "WECHAT_PAY_MCH_ID", "mch-pay-query-refund-race-r44"
        )
        monkeypatch.setattr(
            settings,
            "WECHAT_MINIAPP_APP_ID",
            "appid-pay-query-refund-race-r44",
        )
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
        raw_body = _notify_body()

        all_claims_committed = asyncio.Event()
        both_snapshots_read = asyncio.Barrier(2)
        winner_committed = asyncio.Event()
        observed_handles: set[int] = set()
        payment_handle_key = id(payment_handle)
        refund_handle_key = id(refund_handle)
        claim_committed = {
            payment_handle_key: asyncio.Event(),
            refund_handle_key: asyncio.Event(),
        }
        original_claim_notify_key = notify_intake.claim_notify_key
        original_get_order = OrderRepo.get_order

        async def commit_claims_before_business(
            db,
            message_key: str,
            payload: dict | None = None,
            *,
            lease_seconds: int = notify_intake.DEFAULT_NOTIFY_LEASE_SECONDS,
        ) -> dict:
            """先提交两个 inbox 认领，避免业务快照早于对方认领提交。"""
            claim = await original_claim_notify_key(
                db,
                message_key,
                payload,
                lease_seconds=lease_seconds,
            )
            handle_key = id(db)
            if handle_key in {payment_handle_key, refund_handle_key}:
                await db.commit()
                claim_committed[handle_key].set()
                if all(event.is_set() for event in claim_committed.values()):
                    all_claims_committed.set()
                await asyncio.wait_for(all_claims_committed.wait(), timeout=5)
            return claim

        async def read_old_snapshot_together(
            repo: OrderRepo,
            order_id: str,
        ):
            """让两个事务先读同一 partial 快照，再只允许指定入口提交。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if (
                order_id == ORDER_ID
                and handle_key in {payment_handle_key, refund_handle_key}
                and handle_key not in observed_handles
            ):
                observed_handles.add(handle_key)
                await asyncio.wait_for(both_snapshots_read.wait(), timeout=5)
                role = "payment" if handle_key == payment_handle_key else "refund"
                if role != first_winner:
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(
            notify_intake, "claim_notify_key", commit_claims_before_business
        )
        monkeypatch.setattr(OrderRepo, "get_order", read_old_snapshot_together)

        async def run_payment() -> tuple[str, dict | str]:
            result = await _attempt_payment_query(payment_service)
            if first_winner == "payment":
                winner_committed.set()
            return result

        async def run_refund() -> tuple[str, dict | str]:
            result = await _attempt_refund_notify(refund_service, raw_body)
            if first_winner == "refund":
                winner_committed.set()
            return result

        payment_result, refund_result = await asyncio.gather(
            run_payment(),
            run_refund(),
        )

        initial_inbox_rows = await refund_connection.execute_fetchall(
            "SELECT message_key, status, attempt_count, last_error "
            "FROM inbox_events WHERE message_key IN (?, ?) ORDER BY message_key",
            (PAYMENT_KEY, REFUND_KEY),
        )
        initial_inbox = {str(row["message_key"]): row for row in initial_inbox_rows}
        winner_key = PAYMENT_KEY if first_winner == "payment" else REFUND_KEY
        loser_key = REFUND_KEY if first_winner == "payment" else PAYMENT_KEY
        winner_result = payment_result if first_winner == "payment" else refund_result
        loser_result = refund_result if first_winner == "payment" else payment_result
        assert observed_handles == {payment_handle_key, refund_handle_key}
        assert winner_result[0] == "ok"
        assert loser_result[0] == "locked"
        assert str(initial_inbox[winner_key]["status"]) == "processed"
        assert int(initial_inbox[winner_key]["attempt_count"]) == 1
        assert str(initial_inbox[loser_key]["status"]) == "failed"
        assert int(initial_inbox[loser_key]["attempt_count"]) == 1
        assert "locked" in str(initial_inbox[loser_key]["last_error"]).lower()

        await refund_connection.execute(
            "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
            "WHERE message_key = ?",
            (loser_key,),
        )
        await refund_connection.commit()
        if first_winner == "payment":
            retry_result = await _attempt_refund_notify(refund_service, raw_body)
        else:
            retry_result = await _attempt_payment_query(payment_service)
        assert retry_result[0] == "ok"

        duplicate_payment = await _attempt_payment_query(payment_service)
        await payment_handle.commit()
        duplicate_refund = await _attempt_refund_notify(refund_service, raw_body)
        await refund_handle.commit()
        assert duplicate_payment[0] == "ok"
        assert duplicate_payment[1].get("paymentStatus") == "paid"
        assert duplicate_refund == (
            "ok",
            {"duplicate": True, "kind": "duplicate"},
        )

        state = await _read_final_state(payment_connection)
        _assert_common_final_state(state, first_winner)
        if first_winner == "payment":
            _assert_payment_first_assets(state)
        else:
            _assert_refund_first_assets(state)
    finally:
        await close_db(refund_connection)
        await close_db(payment_connection)
