"""MiniApp 核心闭环 r43：支付通知与查询恢复并发候选复核。"""

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
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
)

ORDER_ID = "order_pay_notify_query_race_r43_001"
OPENID = "pay_notify_query_race_r43_001"
USER_ID = f"wx_{OPENID}"
MOBILE = "13800003043"
COUPON_ID = "coupon_pay_notify_query_race_r43_001"
ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 1_000
BALANCE_FEN = 2_000
EXTERNAL_FEN = ORDER_AMOUNT_FEN - COUPON_FEN - BALANCE_FEN
INITIAL_BALANCE_FEN = 20_000
EXPECTED_AWARD_POINTS = EXTERNAL_FEN // 100
TRANSACTION_ID = "4200000000202609251234567943"
EVENT_ID = "EV-pay-notify-query-race-r43-001"
NOTIFY_KEY = f"wechat_pay_notify:{EVENT_ID}"
QUERY_KEY = f"wechat_pay_notify:query:pay:{ORDER_ID}:{TRANSACTION_ID}"


class _LocalWechatPay:
    """为组合预下单与通知运行时提供不触网的本地支付集成。"""

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
            appid="appid-pay-query-race-r43",
        )

    def build_payment_params(
        self,
        prepay_id: str,
        *,
        signer,
    ) -> dict:
        return {
            "timeStamp": "1789756800",
            "nonceStr": "nonce-r43",
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
    """构建真实支付通知与查询恢复入口。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=_LocalWechatPay(),
        event_repo=OrderEventRepo(handle),
    )


def _payment_transaction() -> dict:
    """构造通知和查询共用的微信支付成功事实。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": "mch-pay-query-race-r43",
        "appid": "appid-pay-query-race-r43",
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T12:00:00+08:00",
    }


def _notify_body() -> bytes:
    """构造支付成功通知外层载荷。"""
    return json.dumps(
        {
            "id": EVENT_ID,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {"kind": "payment"},
        },
        ensure_ascii=False,
    ).encode("utf-8")


async def _seed_order_member_and_coupon(connection: aiosqlite.Connection) -> None:
    """写入待支付订单、会员身份、足额余额和一张可用券。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '支付通知查询竞态会员', 'high', 1)",
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
                        "product_id": "p_pay_notify_query_r43",
                        "title": "支付通知查询竞态蛋糕",
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
    template_id = "cg_pay_notify_query_race_r43_001"
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=template_id,
            name="支付通知查询竞态测试券",
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
            title="支付通知查询竞态测试券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id=template_id,
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


async def _attempt_notify(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, dict | str]:
    """执行通知入口并区分业务冲突与瞬时锁冲突。"""
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


async def _attempt_query(
    service: OrderPaymentRuntimeService,
) -> tuple[str, dict | str]:
    """执行查询恢复入口并区分业务冲突与瞬时锁冲突。"""
    try:
        result = await service.reconcile_pay_from_query(_payment_transaction())
        return "ok", result
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _retry_failed_inbox(
    connection: aiosqlite.Connection,
    failed_keys: list[str],
    notify_service: OrderPaymentRuntimeService,
    query_service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> None:
    """按生产 inbox 路径逐个重投首次锁冲突入口。"""
    for failed_key in failed_keys:
        await connection.execute(
            "UPDATE inbox_events SET next_attempt_at = "
            "datetime('now', '-1 second') WHERE message_key = ?",
            (failed_key,),
        )
        await connection.commit()
        if failed_key == NOTIFY_KEY:
            retry_result = await _attempt_notify(notify_service, raw_body)
        else:
            retry_result = await _attempt_query(query_service)
        assert retry_result[0] == "ok"
        if len(failed_keys) == 1:
            assert retry_result[1].get("paymentStatus") == "paid"


async def _read_final_state(
    connection: aiosqlite.Connection,
) -> dict[str, list[dict]]:
    """读取订单、交易、事件、资产和 inbox 最终事实。"""
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
        "events": (
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "inbox": (
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key IN (?, ?) ORDER BY message_key",
            (NOTIFY_KEY, QUERY_KEY),
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


def _assert_single_settlement(state: dict[str, list[dict]]) -> None:
    """断言并发后只形成一个支付事实和一套资产结算。"""
    assert len(state["orders"]) == 1
    assert str(state["orders"][0]["status"]) == "pending"
    payment = json.loads(str(state["orders"][0]["payment"]))
    assert payment["status"] == "paid"
    assert payment["method"] == "combined"
    assert payment["transactionId"] == TRANSACTION_ID
    assert int(payment["couponFen"]) == COUPON_FEN
    assert int(payment["balanceFen"]) == BALANCE_FEN
    assert int(payment["externalPaidFen"]) == EXTERNAL_FEN
    assert int(payment["pointsAwarded"]) == EXPECTED_AWARD_POINTS
    assert [dict(row) for row in state["transactions"]] == [{"order_id": ORDER_ID}]
    assert [dict(row) for row in state["events"]] == [
        {"status": "paid", "operator": "wechat-pay"}
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
    ]


@pytest.mark.asyncio
async def test_payment_notify_and_query_race_preserves_single_settlement(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """通知与查询同时到达时只能产生一笔支付事实和一次资产结算。"""
    database_path = tmp_path / "pay-notify-query-race-r43.db"
    notify_connection = await init_db(str(database_path))
    query_connection = await init_db(str(database_path))
    notify_handle = DatabaseHandle(notify_connection)
    query_handle = DatabaseHandle(query_connection)
    try:
        await _seed_order_member_and_coupon(notify_connection)
        await _prepare_combined_partial(notify_connection)
        notify_service = _build_runtime_service(notify_handle)
        query_service = _build_runtime_service(query_handle)
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-pay-query-race-r43")
        monkeypatch.setattr(
            settings,
            "WECHAT_MINIAPP_APP_ID",
            "appid-pay-query-race-r43",
        )
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_verify_wechat_notify_signature",
            lambda self, raw_body, headers: True,
        )
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_decrypt_wechat_resource",
            lambda self, resource: _payment_transaction(),
        )
        raw_body = _notify_body()

        both_snapshots_read = asyncio.Event()
        observed_handles: set[int] = set()
        notify_handle_key = id(notify_handle)
        query_handle_key = id(query_handle)
        original_get_order = OrderRepo.get_order

        async def read_old_snapshot_together(
            repo: OrderRepo,
            order_id: str,
        ):
            """让两条入口先读同一组合支付 partial 快照，再并发提交。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if (
                order_id == ORDER_ID
                and handle_key in {notify_handle_key, query_handle_key}
                and handle_key not in observed_handles
            ):
                observed_handles.add(handle_key)
                if len(observed_handles) == 2:
                    both_snapshots_read.set()
                await asyncio.wait_for(both_snapshots_read.wait(), timeout=5)
            return order

        monkeypatch.setattr(OrderRepo, "get_order", read_old_snapshot_together)

        notify_result, query_result = await asyncio.gather(
            _attempt_notify(notify_service, raw_body),
            _attempt_query(query_service),
        )

        initial_inbox_rows = await query_connection.execute_fetchall(
            "SELECT message_key, status, attempt_count, last_error "
            "FROM inbox_events WHERE message_key IN (?, ?) ORDER BY message_key",
            (NOTIFY_KEY, QUERY_KEY),
        )
        assert observed_handles == {notify_handle_key, query_handle_key}
        assert {notify_result[0], query_result[0]} <= {"locked", "ok"}
        assert {str(row["status"]) for row in initial_inbox_rows} <= {
            "failed",
            "processed",
        }
        assert sorted(int(row["attempt_count"]) for row in initial_inbox_rows) == [
            1,
            1,
        ]

        failed_keys = [
            str(row["message_key"])
            for row in initial_inbox_rows
            if str(row["status"]) == "failed"
        ]
        await _retry_failed_inbox(
            query_connection,
            failed_keys,
            notify_service,
            query_service,
            raw_body,
        )

        duplicate_notify = await _attempt_notify(notify_service, raw_body)
        await notify_handle.commit()
        duplicate_query = await _attempt_query(query_service)
        await query_handle.commit()
        assert duplicate_notify == ("ok", {"duplicate": True})
        assert duplicate_query[0] == "ok"
        assert duplicate_query[1]["paymentStatus"] == "paid"

        state = await _read_final_state(notify_connection)
        _assert_single_settlement(state)
        assert {
            str(row["message_key"]): str(row["status"]) for row in state["inbox"]
        } == {
            NOTIFY_KEY: "processed",
            QUERY_KEY: "processed",
        }
        # 两个入口都可能在旧快照竞争时遇到一次 SQLite 瞬时锁并重试。
        final_attempt_counts = sorted(
            int(row["attempt_count"]) for row in state["inbox"]
        )
        assert all(1 <= attempt_count <= 2 for attempt_count in final_attempt_counts)
    finally:
        await close_db(query_connection)
        await close_db(notify_connection)
