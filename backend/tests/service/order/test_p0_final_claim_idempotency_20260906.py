"""P0/P1 最终整改失败测试：先复现缺陷，再验证修复。

覆盖新规 P0-1（通知状态机与原子认领）、P0-2（退款结构化确认语义）、
P0-3（退款三腿同一事务）、P0-4（幂等主体绑定与原结果重放）、
P0-5（金额严格相等与十进制边界）、P1-2（生产鉴权默认开启）。
"""

import json
from contextlib import asynccontextmanager

import pytest

from app.config import settings
from app.models.order import Order, OrderStatus
from app.repository.order_repo import OrderRepo
from app.repository.refund_operation_repo import RefundOperationRepo
from app.service.order.notify_intake import (
    build_notify_key,
    claim_notify,
    complete_notify,
    fail_notify,
)
from app.service.points.ledger import PointsLedgerService
from app.service.stored_value.member import MemberBalanceService


def _paid_payment() -> str:
    """构造无腿已支付快照，外部实付即订单总额。"""
    return json.dumps(
        {
            "status": "paid",
            "method": "wechat",
            "paidAt": "2026-09-06 12:00:00",
            "transactionId": "4200000000202609060000000001",
            "couponFen": 0,
            "balanceFen": 0,
            "pointsFen": 0,
            "pointsUsed": 0,
            "pointsAwarded": 0,
        }
    )


async def _seed_paid_order(db, order_id: str, total_yuan: float) -> None:
    """直写已支付订单，聚焦通知与退款链路。"""
    await db.execute(
        "INSERT OR IGNORE INTO sessions (id, channel, user_id, status) "
        "VALUES (?, ?, ?, ?)",
        ("session-p0final", "miniapp", "wx_openid_p0final", "active"),
    )
    await OrderRepo(db).create_order(
        Order(
            id=order_id,
            session_id="session-p0final",
            channel="miniapp",
            user_id="wx_openid_p0final",
            products="[]",
            total_amount=total_yuan,
            delivery="{}",
            payment=_paid_payment(),
            status=OrderStatus.PENDING,
            remark="",
            created_at="2026-09-06 12:00:00",
            updated_at="2026-09-06 12:00:00",
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_p01_only_processed_is_duplicate(db) -> None:
    """P0-1：只有 processed 才算重复，received 必须可重新认领。"""
    first = await claim_notify(db, "evt-p01-a", lease_seconds=60)
    assert first["decision"] == "claimed"
    # 同一事件在业务完成前再次认领不得判 duplicate（否则永久跳过）。
    second = await claim_notify(db, "evt-p01-a", lease_seconds=60)
    assert second["decision"] != "duplicate"
    await complete_notify(db, "evt-p01-a", first["claim_token"])
    third = await claim_notify(db, "evt-p01-a", lease_seconds=60)
    assert third["decision"] == "duplicate"
    await db.commit()


@pytest.mark.asyncio
async def test_p01_retryable_failed_reclaimable(db) -> None:
    """P0-1：可重试失败在退避到期后必须能被重新认领，而不是永久跳过。"""
    claimed = await claim_notify(db, "evt-p01-b", lease_seconds=60)
    assert claimed["decision"] == "claimed"
    await fail_notify(
        db, "evt-p01-b", claimed["claim_token"], "系统异常", retryable=True
    )
    busy = await claim_notify(db, "evt-p01-b", lease_seconds=60)
    assert busy["decision"] == "processing"
    await db.execute(
        "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
        "WHERE message_key = ?",
        (build_notify_key("evt-p01-b"),),
    )
    again = await claim_notify(db, "evt-p01-b", lease_seconds=60)
    assert again["decision"] == "claimed"
    assert again["attempt_count"] == claimed["attempt_count"] + 1
    await db.commit()


@pytest.mark.asyncio
async def test_p01_stale_claim_token_rejected(db) -> None:
    """P0-1：陈旧 worker 的 claim token 不得提交完成标记。"""
    first = await claim_notify(db, "evt-p01-c", lease_seconds=60)
    # 租约被新 worker 接管（模拟超时后重认领）。
    await db.execute(
        "UPDATE inbox_events SET status = 'received', lease_until = NULL "
        "WHERE message_key = ?",
        (build_notify_key("evt-p01-c"),),
    )
    second = await claim_notify(db, "evt-p01-c", lease_seconds=60)
    assert second["decision"] == "claimed"
    with pytest.raises(ValueError, match="认领已过期|claim"):
        await complete_notify(db, "evt-p01-c", first["claim_token"])
    await complete_notify(db, "evt-p01-c", second["claim_token"])
    await db.commit()


@pytest.mark.asyncio
async def test_p01_concurrent_claim_single_winner(db) -> None:
    """P0-1：并发认领同一事件只有一个胜者，败者不得判重复成功。"""
    results = []
    for _ in range(2):
        results.append(await claim_notify(db, "evt-p01-d", lease_seconds=60))
    decisions = sorted(r["decision"] for r in results)
    assert decisions == ["claimed", "processing"]
    await db.commit()


@pytest.mark.asyncio
async def test_p02_refund_outcome_kinds_recorded(db, monkeypatch) -> None:
    """P0-2：交易号不一致等已建案结果必须携带 rejected_recorded 结构化语义。"""
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-p02")
    await _seed_paid_order(db, "order-p02-a", 10.00)
    from app.service.order.refund_notification import WechatRefundNotificationService

    service = WechatRefundNotificationService(OrderRepo(db))
    result = await service.apply_refund_notify(
        _refund_notify(
            out_trade_no="order-p02-a",
            out_refund_no="refund-p02-a",
            transaction_id="WRONG-TRANSACTION",
            payer_total_fen=1000,
            payer_refund_fen=1000,
        )
    )
    assert result.get("kind") == "rejected_recorded"
    assert result.get("outRefundNo") == "refund-p02-a"
    case_rows = await db.execute_fetchall(
        "SELECT unique_id FROM points_refund_reconcile "
        "WHERE order_id = ? AND unique_id LIKE 'refund:transaction_mismatch:%'",
        ("order-p02-a",),
    )
    assert len(case_rows) == 1


def _refund_notify(
    *,
    out_trade_no: str,
    out_refund_no: str,
    transaction_id: str,
    payer_total_fen: int,
    payer_refund_fen: int,
):
    """构造退款通知规整对象，聚焦确认语义不断言密码学路径。"""
    from app.service.order.wechat_normalizers import RefundNotify

    return RefundNotify(
        out_trade_no=out_trade_no,
        out_refund_no=out_refund_no,
        refund_id="refund-id-p02",
        transaction_id=transaction_id,
        refund_status="SUCCESS",
        success_time="2026-09-06T12:00:00+08:00",
        total_fen=payer_total_fen,
        refund_fen=payer_refund_fen,
        payer_total_fen=payer_total_fen,
        payer_refund_fen=payer_refund_fen,
        user_received_account="",
        mchid="mch-p02",
    )


@pytest.mark.asyncio
async def test_p02_rejected_recorded_maps_http_200() -> None:
    """P0-2：已完整记录事件/案件的拒绝必须映射为微信协议成功确认。"""
    from app.api.channels.storefront.payments import refund_result_to_http_status

    assert refund_result_to_http_status({"kind": "rejected_recorded"}) == 200
    assert refund_result_to_http_status({"kind": "duplicate"}) == 200
    assert refund_result_to_http_status({"kind": "acknowledged"}) == 200


@pytest.mark.asyncio
async def test_p03_refund_three_legs_single_uow(db, monkeypatch) -> None:
    """P0-3：三腿任一失败必须整体回滚，事件与首腿痕迹不得残留。"""
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-p03")
    await _seed_paid_order(db, "order-p03-a", 5.00)
    from app.service.coupon import CouponService
    from app.service.order.refund_notification import WechatRefundNotificationService
    from app.service.points.payment import PointsPaymentService

    async def _leg_ok(order) -> None:
        await RefundOperationRepo(db).append(
            order_id=order.id,
            mobile="",
            member_balance_id=None,
            operation_key=f"probe:leg-ok:{order.id}",
            points_used=0,
            points_awarded=0,
            return_amount=0,
            clawback_amount=0,
            shortfall_amount=0,
            status="succeeded",
            note="首腿探针",
        )

    async def _leg_fail(order) -> None:
        raise RuntimeError("第二腿补偿失败")

    monkeypatch.setattr(
        CouponService, "refund_coupon", lambda self, order: _leg_ok(order)
    )
    monkeypatch.setattr(
        PointsPaymentService,
        "refund_points",
        lambda self, order: _leg_fail(order),
    )
    service = WechatRefundNotificationService(OrderRepo(db))
    with pytest.raises(RuntimeError, match="第二腿补偿失败"):
        await service.apply_refund_notify(
            _refund_notify_p03("order-p03-a", "refund-p03-a")
        )
    event_rows = await db.execute_fetchall(
        "SELECT out_refund_no FROM wechat_refund_events WHERE out_refund_no = ?",
        ("refund-p03-a",),
    )
    leg_rows = await db.execute_fetchall(
        "SELECT operation_key FROM refund_operation WHERE operation_key = ?",
        ("probe:leg-ok:order-p03-a",),
    )
    assert event_rows == []
    assert leg_rows == []


def _refund_notify_p03(order_id: str, out_refund_no: str):
    """构造全额退款通知规整对象，外部实付 500 分。"""
    from app.service.order.wechat_normalizers import RefundNotify

    return RefundNotify(
        out_trade_no=order_id,
        out_refund_no=out_refund_no,
        refund_id="refund-id-p03",
        transaction_id="4200000000202609060000000001",
        refund_status="SUCCESS",
        success_time="2026-09-06T12:00:00+08:00",
        total_fen=500,
        refund_fen=500,
        payer_total_fen=500,
        payer_refund_fen=500,
        user_received_account="",
        mchid="mch-p03",
    )


@pytest.mark.asyncio
async def test_p04_same_key_different_principal_conflict(db) -> None:
    """P0-4：同键不同账户主体必须抛幂等冲突，不得跨账户重放。"""
    from app.service.idempotency import IdempotencyConflict

    service = MemberBalanceService()
    async with _scoped_db(db):
        await service.credit(
            user_id="u-p04",
            mobile="13800001111",
            amount_fen=100,
            biz_type="recharge",
            biz_id="b-p04",
            unique_id="sv-p04-cross",
            source="recharge",
        )
    with pytest.raises(IdempotencyConflict):
        async with _scoped_db(db):
            await service.credit(
                user_id="u-p04",
                mobile="13800002222",
                amount_fen=100,
                biz_type="recharge",
                biz_id="b-p04",
                unique_id="sv-p04-cross",
                source="recharge",
            )


@pytest.mark.asyncio
async def test_p04_replay_returns_original_result(db) -> None:
    """P0-4：重放必须返回原流水的余额快照，不得读取当前余额冒充。"""
    service = MemberBalanceService()
    async with _scoped_db(db):
        await service.credit(
            user_id="u-p04b",
            mobile="13800003333",
            amount_fen=300,
            biz_type="recharge",
            biz_id="b-p04b",
            unique_id="sv-p04b-seed",
            source="recharge",
        )
        first = await service.deduct(
            user_id="u-p04b",
            mobile="13800003333",
            amount_fen=100,
            biz_type="order_pay",
            biz_id="o-p04b",
            unique_id="sv-p04b-deduct",
            source="order",
        )
        assert first == 200
        await service.credit(
            user_id="u-p04b",
            mobile="13800003333",
            amount_fen=50,
            biz_type="recharge",
            biz_id="b-p04b-2",
            unique_id="sv-p04b-seed-2",
            source="recharge",
        )
        replay = await service.deduct(
            user_id="u-p04b",
            mobile="13800003333",
            amount_fen=100,
            biz_type="order_pay",
            biz_id="o-p04b",
            unique_id="sv-p04b-deduct",
            source="order",
        )
    assert replay == 200


@pytest.mark.asyncio
async def test_p04_points_same_key_different_biz_conflict(db) -> None:
    """P0-4：积分同键不同业务必须冲突，同键异额也必须冲突。"""
    from app.service.idempotency import IdempotencyConflict

    service = PointsLedgerService()
    async with _scoped_db(db):
        await service.credit(
            mobile="13800004444",
            amount=100,
            biz_type="order_award",
            biz_id="o-p04c",
            unique_id="pts-p04c",
            event_type="order_award",
        )
    with pytest.raises(IdempotencyConflict):
        async with _scoped_db(db):
            await service.credit(
                mobile="13800004444",
                amount=100,
                biz_type="order_refund",
                biz_id="o-p04c",
                unique_id="pts-p04c",
                event_type="order_refund",
            )
    with pytest.raises(IdempotencyConflict):
        async with _scoped_db(db):
            await service.credit(
                mobile="13800004444",
                amount=200,
                biz_type="order_award",
                biz_id="o-p04c",
                unique_id="pts-p04c",
                event_type="order_award",
            )


@pytest.mark.asyncio
async def test_p05_pay_query_strict_amount_equality(db, monkeypatch) -> None:
    """P0-5：支付金额必须严格相等，少付/多付一律拒绝。"""
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-p05")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-p05")
    await _seed_paid_order(db, "order-p05-a", 10.00)
    from app.repository.config_repo import ConfigRepo
    from app.repository.session_repo import SessionRepo
    from app.repository.youzan_inventory_repo import YouzanInventoryRepo
    from app.repository.youzan_repo import YouzanProductRepo
    from app.service.order import OrderApplicationService

    service = OrderApplicationService(
        order_repo=OrderRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )
    with pytest.raises(ValueError, match="金额"):
        await service.reconcile_pay_from_query(
            {
                "out_trade_no": "order-p05-a",
                "transaction_id": "4200000000202609060000000002",
                "trade_state": "SUCCESS",
                "mchid": "mch-p05",
                "appid": "appid-p05",
                "amount": {"total": 999, "currency": "CNY"},
                "success_time": "2026-09-06T12:00:00+08:00",
            }
        )
    with pytest.raises(ValueError, match="金额"):
        await service.reconcile_pay_from_query(
            {
                "out_trade_no": "order-p05-a",
                "transaction_id": "4200000000202609060000000003",
                "trade_state": "SUCCESS",
                "mchid": "mch-p05",
                "appid": "appid-p05",
                "amount": {"total": 1001, "currency": "CNY"},
                "success_time": "2026-09-06T12:00:00+08:00",
            }
        )


def test_p05_decimal_money_boundaries() -> None:
    """P0-5：1 分精确、半分半向上、非法输入拒绝、十进制字符串往返。"""
    from app.utils import fen_to_yuan_str, yuan_to_fen

    assert yuan_to_fen("0.01") == 1
    assert yuan_to_fen("0.005") == 1
    assert yuan_to_fen(1) == 100
    assert fen_to_yuan_str(1) == "0.01"
    assert yuan_to_fen(fen_to_yuan_str(1999)) == 1999
    for bad in ("nan", "inf", "-inf", "", "abc", None):
        with pytest.raises(ValueError):
            yuan_to_fen(bad)
    with pytest.raises(ValueError):
        yuan_to_fen("-1")


def test_p12_employee_auth_defaults_closed() -> None:
    """P1-2：员工鉴权默认必须开启，关闭只能显式配置。"""
    from app.config import Settings

    assert Settings().WECOM_EMPLOYEE_AUTH_REQUIRED is True


@asynccontextmanager
async def _scoped_db(db):
    """把内存直连包装为仓储可用的事务句柄作用域。"""
    from app.repository.base import DatabaseHandle

    handle = DatabaseHandle(db)
    token = None
    try:
        from app.database import db_conn_var

        token = db_conn_var.set(handle)
        yield handle
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    finally:
        if token is not None:
            from app.database import db_conn_var

            db_conn_var.reset(token)
