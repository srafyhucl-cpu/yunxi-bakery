"""MiniApp 核心闭环 r48：用户取消与微信支付通知并发候选复核。"""

import asyncio
import json
import sqlite3

import pytest

from app.config import settings
from app.database import close_db, init_db
from app.models.order import OrderStatus
from app.repository.base import DatabaseHandle
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.order import notify_intake
from app.service.order.cancellation import OrderCancellationService
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from tests.service.order.test_core_loop_candidate_r41 import (
    EXTERNAL_FEN,
    ORDER_ID,
    TRANSACTION_ID,
    USER_ID,
    _build_cancellation_service,
    _seed_combined_order,
)
from tests.service.order.test_core_loop_candidate_r47 import (
    _assert_payment_recovery,
    _read_final_state,
)

PAYMENT_EVENT_ID = "EV-cancel-payment-notify-race-r48-001"
INBOX_KEY = f"wechat_pay_notify:{PAYMENT_EVENT_ID}"


class _NotifyWechat:
    """只为支付通知提供不触网的时间格式化。"""

    def is_ready(self) -> bool:
        return False

    def format_success_time(self, value: str) -> str:
        return "2026-09-25 12:00:00"


def _build_runtime_service(handle: DatabaseHandle) -> OrderPaymentRuntimeService:
    """构建真实微信支付通知入口。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=_NotifyWechat(),
        event_repo=OrderEventRepo(handle),
    )


def _payment_transaction() -> dict:
    """构造与组合支付外部腿匹配的支付成功通知。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": "mch-cancel-payment-notify-race-r48",
        "appid": "appid-cancel-payment-notify-race-r48",
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T12:00:00+08:00",
    }


def _notify_body() -> bytes:
    """构造本地微信支付通知入口载荷。"""
    return json.dumps(
        {
            "id": PAYMENT_EVENT_ID,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {},
        },
        ensure_ascii=False,
    ).encode("utf-8")


async def _attempt_cancel(
    service: OrderCancellationService,
) -> tuple[str, str]:
    """在生产等价事务中执行用户取消。"""
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


async def _attempt_payment_notify(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, dict | str]:
    """执行支付通知 intake 与入账事务。"""
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


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["cancel", "payment"])
async def test_cancel_and_payment_notify_race_preserves_assets(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    first_winner: str,
) -> None:
    """用户取消与组合支付通知并发时只能形成一套正确资产事实。"""
    database_path = tmp_path / f"cancel-payment-notify-race-{first_winner}-r48.db"
    cancel_connection = await init_db(str(database_path))
    payment_connection = await init_db(str(database_path))
    cancel_handle = DatabaseHandle(cancel_connection)
    payment_handle = DatabaseHandle(payment_connection)
    try:
        await _seed_combined_order(cancel_connection)
        cancel_service = _build_cancellation_service(cancel_handle)
        payment_service = _build_runtime_service(payment_handle)
        monkeypatch.setattr(
            settings,
            "WECHAT_PAY_MCH_ID",
            "mch-cancel-payment-notify-race-r48",
        )
        monkeypatch.setattr(
            settings,
            "WECHAT_MINIAPP_APP_ID",
            "appid-cancel-payment-notify-race-r48",
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

        initial_read_barrier = asyncio.Barrier(2)
        payment_claim_committed = asyncio.Event()
        winner_committed = asyncio.Event()
        observed_handles: set[int] = set()
        cancel_handle_key = id(cancel_handle)
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
            """先提交通知认领，避免取消事务被无关 inbox 提交干扰。"""
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
            """让取消和支付通知先读同一 partial 快照，再固定提交顺序。"""
            handle_key = id(repo._db)
            if (
                order_id == ORDER_ID
                and handle_key == cancel_handle_key
                and handle_key not in observed_handles
            ):
                await asyncio.wait_for(payment_claim_committed.wait(), timeout=5)
            order = await original_get_order(repo, order_id)
            if (
                order_id == ORDER_ID
                and handle_key in {cancel_handle_key, payment_handle_key}
                and handle_key not in observed_handles
            ):
                observed_handles.add(handle_key)
                await asyncio.wait_for(initial_read_barrier.wait(), timeout=5)
                role = "cancel" if handle_key == cancel_handle_key else "payment"
                if role != first_winner:
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(
            notify_intake,
            "claim_notify",
            commit_payment_claim_before_business,
        )
        monkeypatch.setattr(OrderRepo, "get_order", read_old_snapshot_together)

        async def run_cancel() -> tuple[str, str]:
            result = await _attempt_cancel(cancel_service)
            if first_winner == "cancel":
                winner_committed.set()
            return result

        async def run_payment() -> tuple[str, dict | str]:
            result = await _attempt_payment_notify(payment_service, raw_body)
            if first_winner == "payment":
                winner_committed.set()
            return result

        cancel_result, payment_result = await asyncio.gather(
            run_cancel(),
            run_payment(),
        )
        assert observed_handles == {cancel_handle_key, payment_handle_key}
        if first_winner == "cancel":
            assert cancel_result == ("ok", OrderStatus.CANCELLED.value)
            assert payment_result[0] == "locked"
            await payment_connection.execute(
                "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
                "WHERE message_key = ?",
                (INBOX_KEY,),
            )
            await payment_connection.commit()
            payment_result = await _attempt_payment_notify(payment_service, raw_body)
            assert payment_result[0] == "ok"
        else:
            assert payment_result[0] == "ok"
            assert cancel_result[0] == "locked"
            cancel_result = await _attempt_cancel(cancel_service)
            assert cancel_result == ("conflict", "已支付订单不允许取消")

        duplicate_result = await _attempt_payment_notify(payment_service, raw_body)
        await payment_handle.commit()
        assert duplicate_result == ("ok", {"duplicate": True})

        inbox_rows = await payment_connection.execute_fetchall(
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key = ?",
            (INBOX_KEY,),
        )
        assert [dict(row) for row in inbox_rows] == [
            {
                "message_key": INBOX_KEY,
                "status": "processed",
                "attempt_count": 2 if first_winner == "cancel" else 1,
            }
        ]
        state = await _read_final_state(cancel_connection)
        _assert_payment_recovery(state, first_winner == "cancel")
    finally:
        await close_db(payment_connection)
        await close_db(cancel_connection)
