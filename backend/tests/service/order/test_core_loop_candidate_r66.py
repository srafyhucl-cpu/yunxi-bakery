"""MiniApp 核心闭环 r66：已支付组合支付订单全额退款的三腿补偿复核。

复核对象：`_compensate_full_refund` 内的储值腿
`StoredValueOrderPaymentService.refund_order_balance`。

待排除的怀疑：该腿用 `resolve_mobile(order.user_id)` 重新解析当前会员手机号，
且该函数在 openid 身份链缺失或主档手机号为空时抛 ValueError。抛错会让整个
退款事实事务回滚，而微信侧退款已完成。本文件用真实入口验证该怀疑不可达：

- 储值腿要存在（`balanceFen > 0`），必须先经 `prepare_combined_payment` 扣款，
  而扣款前同一 `resolve_mobile(order.user_id)` 已经成功解析过；
- `customer_identity_links` 有 `UNIQUE(tenant_id, identity_type, identity_value)`，
  同一 openid 只能绑定一个主档，不存在解析漂移；
- 全仓唯一会删除身份链接或清空 `customer_master.primary_phone` 的写入方是
  `PrivacyRepo._delete_customer_records`，它与 `DELETE FROM orders` 同事务，
  订单先消失，`_apply_event` 更早就在「订单不存在」处失败。

因此本文件的正向价值是补齐真实三腿补偿的覆盖缺口：既有
`test_full_refund_end_to_end_with_balance_leg` 只带储值腿，
`test_p03_refund_three_legs_single_uow` 用假腿替身，两者都没有跑过
「券已核销 + 积分已结算 + 储值已扣」的真实全额退款。
"""

import json

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.models.coupon import CouponTemplate, CouponType
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.models.order import Order, OrderStatus
from app.repository.base import DatabaseHandle
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.points_ledger_repo import PointsLedgerRepo
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.points import PointsService
from app.service.stored_value.payment import StoredValueOrderPaymentService
from tests.service.order.test_core_loop_candidate_r41 import (
    _build_coupon_service,
    _build_payment_service,
)

MOBILE = "13800003066"
OPENID = "refund_three_legs_r66_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_refund_three_legs_r66_001"
COUPON_ID = "coupon_refund_three_legs_r66_001"
TEMPLATE_ID = "template_refund_three_legs_r66_001"
TRANSACTION_ID = "4200000000202609266600000001"
PAY_EVENT_ID = "EV-refund-three-legs-r66-pay"
REFUND_EVENT_ID = "EV-refund-three-legs-r66-refund"
OUT_REFUND_NO = "R-refund-three-legs-r66-001"
REFUND_ID = "refund-refund-three-legs-r66-001"
MCH_ID = "mch-refund-three-legs-r66"
APP_ID = "appid-refund-three-legs-r66"

ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 1_000
POINTS_USED = 1_000
POINTS_FEN = 1_000
BALANCE_FEN = 2_000
# 10,000 - 1,000 券 - 1,000 积分 - 2,000 储值 = 6,000 分外部支付腿
EXTERNAL_FEN = ORDER_AMOUNT_FEN - COUPON_FEN - POINTS_FEN - BALANCE_FEN
# 6,000 分现金按 1 元 = 1 分向下取整发分。
EXPECTED_AWARD_POINTS = 60
INITIAL_BALANCE_FEN = 20_000
SEED_POINTS = 1_000


class _LocalWechatPay:
    """为支付与退款通知提供不触网的本地集成。"""

    def __init__(self) -> None:
        self.current: dict = {}

    def is_ready(self) -> bool:
        return False

    def verify_notify_signature(
        self,
        raw_body: bytes,
        headers: dict,
        *,
        now_seconds: int | None = None,
    ) -> bool:
        return True

    def decrypt_notify_resource(self, resource: dict) -> dict:
        return dict(self.current)

    def format_success_time(self, value: str) -> str:
        return "2026-09-26 14:00:00"


def _pay_body() -> bytes:
    """构造支付成功通知外层载荷。"""
    return json.dumps(
        {
            "id": PAY_EVENT_ID,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {"kind": "transaction"},
        },
        ensure_ascii=False,
    ).encode("utf-8")


def _refund_body() -> bytes:
    """构造退款成功通知外层载荷。"""
    return json.dumps(
        {
            "id": REFUND_EVENT_ID,
            "event_type": "REFUND.SUCCESS",
            "resource": {"kind": "refund", "order_id": ORDER_ID},
        },
        ensure_ascii=False,
    ).encode("utf-8")


def _pay_transaction() -> dict:
    """构造与组合支付外部腿金额完全匹配的支付成功事实。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": MCH_ID,
        "appid": APP_ID,
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-26T14:00:00+08:00",
    }


def _refund_transaction() -> dict:
    """构造覆盖外部支付腿的全额退款成功事实。"""
    return {
        "mchid": MCH_ID,
        "out_trade_no": ORDER_ID,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": OUT_REFUND_NO,
        "refund_id": REFUND_ID,
        "refund_status": "SUCCESS",
        "success_time": "2026-09-26T15:00:00+08:00",
        "amount": {
            "total": EXTERNAL_FEN,
            "refund": EXTERNAL_FEN,
            "payer_total": EXTERNAL_FEN,
            "payer_refund": EXTERNAL_FEN,
        },
    }


async def _seed_member_and_order(connection: aiosqlite.Connection) -> None:
    """写入会员身份链、储值与积分账户行和待支付订单。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '退款三腿会员', 'high', 1)",
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
        "VALUES (?, ?, ?)",
        (MOBILE, INITIAL_BALANCE_FEN, SEED_POINTS),
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
            payment=json.dumps(build_initial_payment(now_text()), ensure_ascii=False),
            status=OrderStatus.PENDING,
            remark="",
            created_at=now_text(),
            updated_at=now_text(),
        )
    )
    await connection.commit()


async def _seed_coupon(connection: aiosqlite.Connection) -> None:
    """写入可用的满减券模板与 TAKE 库存行。"""
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=TEMPLATE_ID,
            name="退款三腿测试券",
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
            title="退款三腿测试券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id=TEMPLATE_ID,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()


async def _build_paid_combined_legs(
    connection: aiosqlite.Connection,
    handle: DatabaseHandle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """用真实服务把订单推进到券已应用、积分已应用、储值已扣的 partial 态。"""
    coupon_service = _build_coupon_service(handle)
    await coupon_service.apply_coupon(ORDER_ID, user_id=USER_ID, coupon_id=COUPON_ID)
    # 解除 B3.4 临时围栏，走真实积分抵扣入口（与 test_points_payment 同口径）。
    monkeypatch.setattr("app.service.points.payment.POINTS_DEDUCTION_FENCE", False)
    points_service = PointsService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=PointsLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
        order_repo=OrderRepo(handle),
    )
    applied = await points_service.apply_points(ORDER_ID, user_id=USER_ID)
    assert int(applied["pointsUsed"]) == POINTS_USED
    await _build_payment_service(handle).prepare_combined_payment(
        ORDER_ID,
        user_id=USER_ID,
        balance_fen=BALANCE_FEN,
    )
    await connection.commit()


async def _read_state(connection: aiosqlite.Connection) -> dict[str, list[dict]]:
    """读取订单、退款事实、储值流水、积分流水、账户与券的最终事实。"""
    queries = {
        "order": ("SELECT status, payment FROM orders WHERE id = ?", (ORDER_ID,)),
        "refunds": (
            "SELECT out_refund_no, transaction_id, payer_refund_fen, source "
            "FROM wechat_refund_events WHERE order_id = ?",
            (ORDER_ID,),
        ),
        "balance_ledger": (
            "SELECT unique_id, mobile, amount_fen FROM balance_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "points_ledger": (
            "SELECT unique_id, mobile, amount FROM points_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "member": (
            "SELECT stored_value_fen, points FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        ),
        "coupons": (
            "SELECT status, order_no, deducted_fen FROM coupon_inventory "
            "WHERE coupon_id = ? ORDER BY id",
            (COUPON_ID,),
        ),
        "inbox": (
            "SELECT message_key, status, attempt_count FROM inbox_events "
            "WHERE message_key IN (?, ?) ORDER BY message_key",
            (
                f"wechat_pay_notify:{PAY_EVENT_ID}",
                f"wechat_pay_notify:{REFUND_EVENT_ID}",
            ),
        ),
    }
    return {
        name: await connection.execute_fetchall(sql, parameters)
        for name, (sql, parameters) in queries.items()
    }


def _assert_paid_state(state: dict[str, list[dict]]) -> None:
    """断言支付成功后三腿事实齐备：券已核销、积分已结算、储值已扣。"""
    order = state["order"][0]
    payment = json.loads(str(order["payment"]))
    assert str(order["status"]) == OrderStatus.PENDING.value
    assert payment["status"] == "paid"
    assert payment["transactionId"] == TRANSACTION_ID
    assert int(payment["couponFen"]) == COUPON_FEN
    assert int(payment["pointsUsed"]) == POINTS_USED
    assert int(payment["pointsAwarded"]) == EXPECTED_AWARD_POINTS
    assert bool(payment.get("pointsSettledAt"))
    assert int(payment["balanceFen"]) == BALANCE_FEN
    assert [dict(row) for row in state["balance_ledger"]] == [
        {
            "unique_id": f"combined_pay:{ORDER_ID}",
            "mobile": MOBILE,
            "amount_fen": -BALANCE_FEN,
        }
    ]
    assert [dict(row) for row in state["points_ledger"]] == [
        {
            "unique_id": f"points:redeem:{ORDER_ID}",
            "mobile": MOBILE,
            "amount": -POINTS_USED,
        },
        {
            "unique_id": f"points:award:{ORDER_ID}",
            "mobile": MOBILE,
            "amount": EXPECTED_AWARD_POINTS,
        },
    ]
    assert [dict(row) for row in state["member"]] == [
        {
            "stored_value_fen": INITIAL_BALANCE_FEN - BALANCE_FEN,
            "points": SEED_POINTS - POINTS_USED + EXPECTED_AWARD_POINTS,
        }
    ]
    assert [dict(row) for row in state["coupons"]] == [
        {"status": CouponStatus.TAKE, "order_no": "", "deducted_fen": 0},
        {
            "status": CouponStatus.CONSUME,
            "order_no": ORDER_ID,
            "deducted_fen": COUPON_FEN,
        },
    ]


def _assert_refunded_state(state: dict[str, list[dict]]) -> None:
    """断言全额退款后三腿全部回到原账户，且退款事实与通知终态同时落账。"""
    order = state["order"][0]
    payment = json.loads(str(order["payment"]))
    assert str(order["status"]) == OrderStatus.PENDING.value
    assert payment["status"] == "paid"
    assert payment["refundStatus"] == "full"
    assert int(payment["refundFen"]) == EXTERNAL_FEN
    # 关键断言：储值腿退回到与扣款同一账户，`resolve_mobile` 既未把退款
    # 导向其他账户，也未抛错把已到账的微信退款事实回滚掉。
    assert [dict(row) for row in state["balance_ledger"]] == [
        {
            "unique_id": f"combined_pay:{ORDER_ID}",
            "mobile": MOBILE,
            "amount_fen": -BALANCE_FEN,
        },
        {
            "unique_id": f"order_refund:{ORDER_ID}",
            "mobile": MOBILE,
            "amount_fen": BALANCE_FEN,
        },
    ]
    assert [dict(row) for row in state["points_ledger"]] == [
        {
            "unique_id": f"points:redeem:{ORDER_ID}",
            "mobile": MOBILE,
            "amount": -POINTS_USED,
        },
        {
            "unique_id": f"points:award:{ORDER_ID}",
            "mobile": MOBILE,
            "amount": EXPECTED_AWARD_POINTS,
        },
        {
            "unique_id": f"points:refund:{ORDER_ID}",
            "mobile": MOBILE,
            "amount": POINTS_USED,
        },
        {
            "unique_id": f"points:refund:{ORDER_ID}:clawback",
            "mobile": MOBILE,
            "amount": -EXPECTED_AWARD_POINTS,
        },
    ]
    assert [dict(row) for row in state["member"]] == [
        {"stored_value_fen": INITIAL_BALANCE_FEN, "points": SEED_POINTS}
    ]
    assert [dict(row) for row in state["coupons"]] == [
        {"status": CouponStatus.TAKE, "order_no": "", "deducted_fen": 0},
        {
            "status": CouponStatus.CONSUME,
            "order_no": ORDER_ID,
            "deducted_fen": COUPON_FEN,
        },
        {
            "status": CouponStatus.BACK,
            "order_no": ORDER_ID,
            "deducted_fen": COUPON_FEN,
        },
        # r78（`M-20260926-028`）：三腿补偿里的券腿现在同时退掉「抵扣事实」
        # （BACK 冲正）与「可持有性」（新周期 TAKE），客户拿回现金后券仍可用。
        {
            "status": CouponStatus.TAKE,
            "order_no": ORDER_ID,
            "deducted_fen": 0,
        },
    ]
    assert [dict(row) for row in state["refunds"]] == [
        {
            "out_refund_no": OUT_REFUND_NO,
            "transaction_id": TRANSACTION_ID,
            "payer_refund_fen": EXTERNAL_FEN,
            "source": "notify",
        }
    ]
    assert [dict(row) for row in state["inbox"]] == [
        {
            "message_key": f"wechat_pay_notify:{PAY_EVENT_ID}",
            "status": "processed",
            "attempt_count": 1,
        },
        {
            "message_key": f"wechat_pay_notify:{REFUND_EVENT_ID}",
            "status": "processed",
            "attempt_count": 1,
        },
    ]


@pytest.mark.asyncio
async def test_full_refund_compensates_all_three_legs_into_original_account(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已支付组合支付订单全额退款必须三腿齐退，且储值腿退到原扣款账户。"""
    database_path = tmp_path / "refund-three-legs-r66.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        await _seed_member_and_order(connection)
        await _seed_coupon(connection)
        await _build_paid_combined_legs(connection, handle, monkeypatch)

        wechat = _LocalWechatPay()
        service = OrderPaymentRuntimeService(
            order_repo=OrderRepo(handle),
            wechat_pay_service=wechat,
            event_repo=OrderEventRepo(handle),
        )

        wechat.current = _pay_transaction()
        pay_result = await service.handle_wechat_payment_notify(
            raw_body=_pay_body(),
            headers={},
        )
        await handle.commit()
        assert pay_result["status"] == OrderStatus.PENDING.value
        _assert_paid_state(await _read_state(connection))

        # 记录储值腿实际执行次数：证明三腿补偿确实跑了，而不是被整体跳过
        # 导致后续断言空转。
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

        wechat.current = _refund_transaction()
        refund_result = await service.handle_wechat_refund_notify(
            raw_body=_refund_body(),
            headers={},
        )
        await handle.commit()
        assert refund_result["kind"] == "acknowledged"
        assert compensate_calls == [ORDER_ID]
        _assert_refunded_state(await _read_state(connection))

        # 重放同一笔退款通知：微信会重复投递，三腿都不得二次补偿。
        repeat = await service.handle_wechat_refund_notify(
            raw_body=_refund_body(),
            headers={},
        )
        await handle.commit()
        assert repeat["kind"] == "duplicate"
        assert compensate_calls == [ORDER_ID]
        _assert_refunded_state(await _read_state(connection))
    finally:
        await close_db(connection)
