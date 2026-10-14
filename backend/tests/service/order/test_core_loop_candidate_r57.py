"""MiniApp 核心闭环 r57：后台确认与微信支付通知并发候选复核。"""

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
from app.service.order import notify_intake
from app.service.integrations.wechat_pay import WechatPayPrepayResult
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.serialization import OrderSerializationService
from app.service.order.status_flow import OrderAdminStatusService
from app.service.order.timeline import OrderTimelineService
from tests.helpers.legacy_order_catalog import (
    LegacyOrderInventoryRepo,
    LegacyOrderProductRepo,
)

ORDER_ID = "order_admin_confirm_payment_race_r57_001"
USER_ID = "wx_admin_confirm_payment_race_r57_001"
OPENID = "admin_confirm_payment_race_r57_001"
MOBILE = "13800003057"
ORDER_AMOUNT_FEN = 10_000
TRANSACTION_ID = "4200000000202609251234567957"


class _LocalWechatPay:
    """提供不触网的本地微信通知集成。"""

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
        """返回本地微信预下单结果，不访问外部网络。"""
        return WechatPayPrepayResult(
            prepay_id=f"prepay-{order_id}-{total_fen}",
            appid="appid-admin-confirm-payment-race-r57",
        )

    def build_payment_params(self, prepay_id: str, *, signer) -> dict:
        """返回可交给小程序端的本地微信支付参数。"""
        return {
            "timeStamp": "1789756800",
            "nonceStr": "nonce-r57",
            "package": f"prepay_id={prepay_id}",
            "signType": "RSA",
            "paySign": signer(f"prepay:{prepay_id}"),
        }

    def sign_with_rsa(self, message: str) -> str:
        """返回确定性的本地签名占位。"""
        return f"signature:{message}"

    def verify_notify_signature(
        self,
        raw_body: bytes,
        headers: dict[str, str],
        *,
        now_seconds: int | None = None,
    ) -> bool:
        return True

    def decrypt_notify_resource(self, resource: dict) -> dict:
        return {
            "out_trade_no": ORDER_ID,
            "trade_state": "SUCCESS",
            "mchid": "mch-admin-confirm-payment-race-r57",
            "appid": "appid-admin-confirm-payment-race-r57",
            "amount": {"total": ORDER_AMOUNT_FEN, "currency": "CNY"},
            "transaction_id": TRANSACTION_ID,
            "success_time": "2026-09-25T12:00:00+08:00",
        }

    def format_success_time(self, value: str) -> str:
        return "2026-09-25 12:00:00"


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


def _build_payment_service(handle: DatabaseHandle) -> OrderPaymentRuntimeService:
    """构建真实微信支付通知运行时。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=_LocalWechatPay(),
        event_repo=OrderEventRepo(handle),
    )


async def _seed_order(connection: aiosqlite.Connection) -> None:
    """写入待支付订单、会员身份和积分结算账户。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '后台确认支付并发会员', "
        "'high', 1)",
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
            products="[]",
            total_amount=ORDER_AMOUNT_FEN / 100,
            delivery="{}",
            payment=json.dumps(
                {
                    "status": "unpaid",
                    "method": "",
                    "createdAt": "2026-09-25 11:00:00",
                },
                ensure_ascii=False,
            ),
            status=OrderStatus.PENDING,
            remark="",
            created_at="2026-09-25 11:00:00",
            updated_at="2026-09-25 11:00:00",
        )
    )
    await connection.commit()


async def _attempt_admin_confirm(
    service: OrderAdminStatusService,
) -> tuple[str, str]:
    """在独立后台请求事务中执行真实确认。"""
    try:
        async with service._order_repo.transaction():
            result = await service.update_admin_order_status(ORDER_ID, "confirmed")
        return "ok", str(result["status"])
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_payment_notify(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, dict | str]:
    """执行真实支付通知入口并区分业务冲突与 SQLite 瞬时锁。"""
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


async def _read_state(connection: aiosqlite.Connection) -> dict[str, list[dict]]:
    """读取订单、交易、事件、资产和 inbox 最终事实。"""
    queries = {
        "order": (
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        ),
        "transaction": (
            "SELECT transaction_id, order_id FROM payment_transactions "
            "WHERE transaction_id = ?",
            (TRANSACTION_ID,),
        ),
        "events": (
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "member": (
            "SELECT stored_value_fen, points FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        ),
        "points_ledger": (
            "SELECT unique_id, event_type, amount, total FROM points_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "inbox": (
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key = ?",
            (f"wechat_pay_notify:{EVENT_ID}",),
        ),
    }
    return {
        name: await connection.execute_fetchall(sql, parameters)
        for name, (sql, parameters) in queries.items()
    }


def _assert_state(
    state: dict[str, list[dict]],
    *,
    first_winner: str,
) -> None:
    """断言确认与支付通知交错后仍只形成一次支付和一次确认事实。"""
    assert len(state["order"]) == 1
    order = state["order"][0]
    payment = json.loads(str(order["payment"]))
    assert str(order["status"]) == OrderStatus.CONFIRMED.value
    assert str(payment["status"]) == "paid"
    assert str(payment["method"]) == "wechat"
    assert str(payment["transactionId"]) == TRANSACTION_ID
    assert int(payment["externalPaidFen"]) == ORDER_AMOUNT_FEN
    assert int(payment["wechatPrepayFen"]) == ORDER_AMOUNT_FEN
    assert [dict(row) for row in state["transaction"]] == [
        {"transaction_id": TRANSACTION_ID, "order_id": ORDER_ID}
    ]
    assert [dict(row) for row in state["events"]] == [
        {"status": "paid", "operator": "wechat-pay"},
        {"status": "confirmed", "operator": "admin"},
    ] or [dict(row) for row in state["events"]] == [
        {"status": "confirmed", "operator": "admin"},
        {"status": "paid", "operator": "wechat-pay"},
    ]
    assert [dict(row) for row in state["member"]] == [
        {"stored_value_fen": 0, "points": ORDER_AMOUNT_FEN // 100}
    ]
    assert [dict(row) for row in state["points_ledger"]] == [
        {
            "unique_id": f"points:award:{ORDER_ID}",
            "event_type": "order_award",
            "amount": ORDER_AMOUNT_FEN // 100,
            "total": ORDER_AMOUNT_FEN // 100,
        }
    ]
    assert [dict(row) for row in state["inbox"]] == [
        {
            "message_key": f"wechat_pay_notify:{EVENT_ID}",
            "status": "processed",
            "attempt_count": 2 if first_winner == "admin" else 1,
        }
    ]


EVENT_ID = "EV-admin-confirm-payment-race-r57-001"


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["admin", "payment"])
async def test_admin_confirm_and_payment_notify_race_preserves_paid_state(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    first_winner: str,
) -> None:
    """后台确认与微信支付通知并发后不得丢失支付事实或重复写事件。"""
    database_path = tmp_path / f"admin-confirm-payment-{first_winner}-r57.db"
    admin_connection = await init_db(str(database_path))
    payment_connection = await init_db(str(database_path))
    admin_handle = DatabaseHandle(admin_connection)
    payment_handle = DatabaseHandle(payment_connection)
    try:
        await _seed_order(payment_connection)
        admin_service = _build_admin_service(admin_handle)
        payment_service = _build_payment_service(payment_handle)
        monkeypatch.setattr(
            settings,
            "WECHAT_PAY_MCH_ID",
            "mch-admin-confirm-payment-race-r57",
        )
        monkeypatch.setattr(
            settings,
            "WECHAT_MINIAPP_APP_ID",
            "appid-admin-confirm-payment-race-r57",
        )
        payment_session = await payment_service.prepare_payment(
            ORDER_ID,
            user_id=USER_ID,
        )
        assert payment_session.mode == "wechat"
        raw_body = json.dumps(
            {
                "id": EVENT_ID,
                "event_type": "TRANSACTION.SUCCESS",
                "resource": {},
            },
            ensure_ascii=False,
        ).encode("utf-8")

        initial_read_barrier = asyncio.Barrier(2)
        payment_claim_committed = asyncio.Event()
        winner_committed = asyncio.Event()
        observed_handles: set[int] = set()
        admin_handle_key = id(admin_handle)
        payment_handle_key = id(payment_handle)
        original_claim_notify = notify_intake.claim_notify
        original_get_order = OrderRepo.get_order

        async def commit_payment_claim_before_business(
            db,
            event_id: str,
            payload: dict | None = None,
            *,
            lease_seconds: int = notify_intake.DEFAULT_NOTIFY_LEASE_SECONDS,
        ) -> dict:
            """先提交通知认领，避免 inbox 写锁改变业务首胜顺序。"""
            claim = await original_claim_notify(
                db,
                event_id,
                payload,
                lease_seconds=lease_seconds,
            )
            if id(db) == payment_handle_key:
                await db.commit()
                payment_claim_committed.set()
            return claim

        async def read_old_snapshot_together(
            repo: OrderRepo,
            order_id: str,
        ):
            """让两个真实入口先读到同一待支付快照，再固定首胜顺序。"""
            handle_key = id(repo._db)
            if order_id == ORDER_ID and handle_key == admin_handle_key:
                await asyncio.wait_for(payment_claim_committed.wait(), timeout=5)
            order = await original_get_order(repo, order_id)
            if (
                order_id == ORDER_ID
                and handle_key in {admin_handle_key, payment_handle_key}
                and handle_key not in observed_handles
            ):
                observed_handles.add(handle_key)
                await asyncio.wait_for(initial_read_barrier.wait(), timeout=5)
                role = "admin" if handle_key == admin_handle_key else "payment"
                if role != first_winner:
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(
            notify_intake,
            "claim_notify",
            commit_payment_claim_before_business,
        )
        monkeypatch.setattr(OrderRepo, "get_order", read_old_snapshot_together)

        async def run_admin() -> tuple[str, str]:
            result = await _attempt_admin_confirm(admin_service)
            if first_winner == "admin":
                winner_committed.set()
            return result

        async def run_payment() -> tuple[str, dict | str]:
            result = await _attempt_payment_notify(payment_service, raw_body)
            if first_winner == "payment":
                winner_committed.set()
            return result

        admin_result, payment_result = await asyncio.gather(
            run_admin(),
            run_payment(),
        )
        assert observed_handles == {admin_handle_key, payment_handle_key}
        assert admin_result[0] in {"ok", "locked"}
        assert payment_result[0] in {"ok", "locked"}
        if admin_result[0] == "locked":
            admin_result = await _attempt_admin_confirm(admin_service)
        if payment_result[0] == "locked":
            await payment_connection.execute(
                "UPDATE inbox_events SET next_attempt_at = "
                "datetime('now', '-1 second') WHERE message_key = ?",
                (f"wechat_pay_notify:{EVENT_ID}",),
            )
            await payment_connection.commit()
            payment_result = await _attempt_payment_notify(payment_service, raw_body)
        assert admin_result == ("ok", OrderStatus.CONFIRMED.value)
        assert payment_result[0] == "ok"

        duplicate_result = await _attempt_payment_notify(payment_service, raw_body)
        await payment_handle.commit()
        assert duplicate_result == ("ok", {"duplicate": True})
        _assert_state(
            await _read_state(payment_connection),
            first_winner=first_winner,
        )
    finally:
        await close_db(payment_connection)
        await close_db(admin_connection)
