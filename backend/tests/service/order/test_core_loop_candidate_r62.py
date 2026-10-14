"""MiniApp 核心闭环 r62：已退款组合支付订单被后台取消时的储值重复补偿复核。"""

import json

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.models.member import CouponStatus
from app.models.order import OrderStatus
from app.repository.base import DatabaseHandle
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.serialization import OrderSerializationService
from app.service.order.status_flow import OrderAdminStatusService
from app.service.order.timeline import OrderTimelineService
from app.service.stored_value.payment import StoredValueOrderPaymentService
from app.service.stored_value import StoredValueService
from tests.helpers.legacy_order_catalog import (
    LegacyOrderInventoryRepo,
    LegacyOrderProductRepo,
)
from tests.service.order.test_core_loop_candidate_r41 import (
    BALANCE_FEN,
    COUPON_ID,
    EXTERNAL_FEN,
    INITIAL_BALANCE_FEN,
    MOBILE,
    ORDER_ID,
    TRANSACTION_ID,
    _build_member_service,
    _build_payment_service,
    _seed_combined_order,
)

EVENT_ID = "EV-refunded-combined-admin-cancel-r62-001"
INBOX_KEY = f"wechat_pay_notify:{EVENT_ID}"
OUT_REFUND_NO = "R-refunded-combined-admin-cancel-r62-001"
REFUND_ID = "refund-refunded-combined-admin-cancel-r62-001"
MCH_ID = "mch-refunded-combined-admin-cancel-r62"
APP_ID = "appid-refunded-combined-admin-cancel-r62"


class _LocalWechatPay:
    """为本地退款通知与支付确认提供不触网的本地集成。"""

    def is_ready(self) -> bool:
        return False

    def format_success_time(self, value: str) -> str:
        return "2026-09-26 10:00:00"


def _build_refund_notify_service(handle: DatabaseHandle) -> OrderPaymentRuntimeService:
    """构建真实微信退款通知入口。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=_LocalWechatPay(),
        event_repo=OrderEventRepo(handle),
    )


def _build_admin_cancel_service(handle: DatabaseHandle) -> OrderAdminStatusService:
    """构建带储值补偿的真实后台订单状态服务。"""
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
        stored_value_service=StoredValueService(
            member_service=_build_member_service(handle),
            payment_service=_build_payment_service(handle),
        ),
    )


def _refund_notify_body() -> bytes:
    """构造一次覆盖外部支付腿的全额退款通知外层载荷。"""
    return json.dumps(
        {
            "id": EVENT_ID,
            "event_type": "REFUND.SUCCESS",
            "resource": {
                "kind": "refund",
                "order_id": ORDER_ID,
                "out_refund_no": OUT_REFUND_NO,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")


def _refund_transaction(resource: dict) -> dict:
    """构造与组合支付外部腿金额完全匹配的全额退款通知内容。"""
    return {
        "mchid": MCH_ID,
        "out_trade_no": ORDER_ID,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": OUT_REFUND_NO,
        "refund_id": REFUND_ID,
        "refund_status": "SUCCESS",
        "success_time": "2026-09-26T10:05:00+08:00",
        "amount": {
            "total": EXTERNAL_FEN,
            "refund": EXTERNAL_FEN,
            "payer_total": EXTERNAL_FEN,
            "payer_refund": EXTERNAL_FEN,
        },
    }


async def _attempt_refund_notify(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, dict | str]:
    """执行真实退款通知入口并区分业务结果与瞬时锁失败。"""
    import sqlite3

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


async def _attempt_admin_cancel(
    service: OrderAdminStatusService,
) -> tuple[str, str]:
    """在生产等价事务中执行真实后台取消。"""
    import sqlite3

    try:
        async with service._order_repo.transaction():
            result = await service.update_admin_order_status(ORDER_ID, "cancelled")
        return "ok", str(result["status"])
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _read_state(connection: aiosqlite.Connection) -> dict[str, list[dict]]:
    """读取订单、退款、交易、储值流水、余额、券和事件最终事实。"""
    queries = {
        "order": (
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        ),
        "refunds": (
            "SELECT out_refund_no, transaction_id, payer_refund_fen, source "
            "FROM wechat_refund_events WHERE order_id = ?",
            (ORDER_ID,),
        ),
        "transactions": (
            "SELECT transaction_id, order_id FROM payment_transactions "
            "WHERE transaction_id = ?",
            (TRANSACTION_ID,),
        ),
        "balance_ledger": (
            "SELECT unique_id, amount_fen FROM balance_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "member": (
            "SELECT stored_value_fen, points FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        ),
        "coupons": (
            "SELECT coupon_id, status, order_no, deducted_fen FROM coupon_inventory "
            "WHERE coupon_id = ? ORDER BY id",
            (COUPON_ID,),
        ),
        "events": (
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "inbox": (
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key = ?",
            (INBOX_KEY,),
        ),
    }
    return {
        name: await connection.execute_fetchall(sql, parameters)
        for name, (sql, parameters) in queries.items()
    }


def _assert_refund_only_state(state: dict[str, list[dict]]) -> None:
    """断言退款先到后的中间态：订单仍 partial、退款终态、储值已原路退回一次。"""
    assert len(state["order"]) == 1
    order = state["order"][0]
    payment = json.loads(str(order["payment"]))
    assert str(order["status"]) == OrderStatus.PENDING.value
    assert payment["status"] == "partial"
    assert int(payment["balanceFen"]) == BALANCE_FEN
    assert int(payment["externalPaidFen"]) == EXTERNAL_FEN
    assert payment["refundStatus"] == "full"
    assert int(payment["refundFen"]) == EXTERNAL_FEN
    assert [dict(row) for row in state["refunds"]] == [
        {
            "out_refund_no": OUT_REFUND_NO,
            "transaction_id": TRANSACTION_ID,
            "payer_refund_fen": EXTERNAL_FEN,
            "source": "notify",
        }
    ]
    assert [dict(row) for row in state["transactions"]] == [
        {"transaction_id": TRANSACTION_ID, "order_id": ORDER_ID}
    ]
    # 组合支付扣款 + 退款原路退回，恰好各一条。
    assert [dict(row) for row in state["balance_ledger"]] == [
        {"unique_id": f"combined_pay:{ORDER_ID}", "amount_fen": -BALANCE_FEN},
        {"unique_id": f"order_refund:{ORDER_ID}", "amount_fen": BALANCE_FEN},
    ]
    assert [dict(row) for row in state["member"]] == [
        {"stored_value_fen": INITIAL_BALANCE_FEN, "points": 0}
    ]
    # 券从未核销，退款补偿不得凭空写入 BACK 行。
    assert [dict(row) for row in state["coupons"]] == [
        {
            "coupon_id": COUPON_ID,
            "status": CouponStatus.TAKE,
            "order_no": "",
            "deducted_fen": 0,
        }
    ]


def _assert_after_admin_cancel(state: dict[str, list[dict]]) -> None:
    """断言后台取消不得二次补偿储值，且退款事实与取消事实同时保留。"""
    assert len(state["order"]) == 1
    order = state["order"][0]
    payment = json.loads(str(order["payment"]))
    assert str(order["status"]) == OrderStatus.CANCELLED.value
    assert payment["status"] == "partial"
    assert payment["refundStatus"] == "full"
    assert int(payment["refundFen"]) == EXTERNAL_FEN
    assert str(payment.get("couponId", "")) == ""
    # 关键断言：储值补偿幂等键保证只有一条退款流水，余额不被重复退回。
    assert [dict(row) for row in state["balance_ledger"]] == [
        {"unique_id": f"combined_pay:{ORDER_ID}", "amount_fen": -BALANCE_FEN},
        {"unique_id": f"order_refund:{ORDER_ID}", "amount_fen": BALANCE_FEN},
    ]
    assert [dict(row) for row in state["member"]] == [
        {"stored_value_fen": INITIAL_BALANCE_FEN, "points": 0}
    ]
    assert [dict(row) for row in state["refunds"]] == [
        {
            "out_refund_no": OUT_REFUND_NO,
            "transaction_id": TRANSACTION_ID,
            "payer_refund_fen": EXTERNAL_FEN,
            "source": "notify",
        }
    ]
    assert [dict(row) for row in state["transactions"]] == [
        {"transaction_id": TRANSACTION_ID, "order_id": ORDER_ID}
    ]
    # 券仍未核销，后台取消只清快照，不得凭空退回。
    assert [dict(row) for row in state["coupons"]] == [
        {
            "coupon_id": COUPON_ID,
            "status": CouponStatus.TAKE,
            "order_no": "",
            "deducted_fen": 0,
        }
    ]
    assert [dict(row) for row in state["events"]] == [
        {"status": OrderStatus.CANCELLED.value, "operator": "admin"}
    ]
    assert [dict(row) for row in state["inbox"]] == [
        {
            "message_key": INBOX_KEY,
            "status": "processed",
            "attempt_count": 1,
        }
    ]


@pytest.mark.asyncio
async def test_admin_cancel_of_refunded_combined_order_does_not_double_credit_balance(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """退款先到使组合支付订单进入 partial+full 后，后台取消不得二次退回储值。"""
    database_path = tmp_path / "refunded-combined-admin-cancel-r62.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        await _seed_combined_order(connection)
        refund_service = _build_refund_notify_service(handle)
        admin_service = _build_admin_cancel_service(handle)
        raw_body = _refund_notify_body()

        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_verify_wechat_notify_signature",
            lambda self, payload, headers: True,
        )
        monkeypatch.setattr(
            OrderPaymentRuntimeService,
            "_decrypt_wechat_resource",
            lambda self, resource: _refund_transaction(resource),
        )

        # 记录储值补偿实际执行次数：必须证明后台取消确实重跑了补偿，
        # 余额只退回一次来自幂等键，而不是补偿被整体跳过（否则断言会空转）。
        compensate_calls: list[str] = []
        original_refund_order_balance = (
            StoredValueOrderPaymentService.refund_order_balance
        )

        async def spy_refund_order_balance(self, order):
            compensate_calls.append(order.id)
            return await original_refund_order_balance(self, order)

        monkeypatch.setattr(
            StoredValueOrderPaymentService,
            "refund_order_balance",
            spy_refund_order_balance,
        )

        # 组合支付订单处于 partial（余额已扣、微信尾款未到账），退款先到。
        refund_result = await _attempt_refund_notify(refund_service, raw_body)
        await handle.commit()
        assert refund_result[0] == "ok"
        _assert_refund_only_state(await _read_state(connection))
        assert compensate_calls == [ORDER_ID]

        # 新增 SQL 允许取消 partial 订单；补偿路径不得二次退回储值。
        cancel_result = await _attempt_admin_cancel(admin_service)
        await handle.commit()
        assert cancel_result == ("ok", OrderStatus.CANCELLED.value)
        # 关键：后台取消确实再次执行了储值补偿，幂等由 order_refund 幂等键保证。
        assert compensate_calls == [ORDER_ID, ORDER_ID]
        _assert_after_admin_cancel(await _read_state(connection))

        # 重复取消与重复退款通知都必须保持幂等，不得产生第二条储值退款流水。
        repeat_cancel = await _attempt_admin_cancel(admin_service)
        await handle.commit()
        assert repeat_cancel[0] == "ok"
        repeat_refund = await _attempt_refund_notify(refund_service, raw_body)
        await handle.commit()
        assert repeat_refund[0] == "ok"
        assert compensate_calls == [ORDER_ID, ORDER_ID]
        _assert_after_admin_cancel(await _read_state(connection))
    finally:
        await close_db(connection)
