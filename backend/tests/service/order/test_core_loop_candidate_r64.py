"""MiniApp 核心闭环 r64：优惠券在应用后、支付前过期时的支付与核销一致性复核。"""

import json

import aiosqlite
import pytest

from app.config import settings
from app.database import init_db
from app.models.coupon import CouponTemplate, CouponType
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.models.order import Order, OrderStatus
from app.repository.base import DatabaseHandle
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment, now_text
from tests.service.order.test_core_loop_candidate_r41 import (
    _build_coupon_service,
)

MOBILE = "13800003064"
OPENID = "coupon_expire_r64_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_coupon_expire_r64_001"
COUPON_ID = "coupon_expire_r64_001"
TEMPLATE_ID = "template_expire_r64_001"
ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 1_000
EXTERNAL_FEN = ORDER_AMOUNT_FEN - COUPON_FEN
TRANSACTION_ID = "4200000000202609266400000001"
EVENT_ID = "EV-coupon-expire-r64-pay"
MCH_ID = "mch-coupon-expire-r64"
APP_ID = "appid-coupon-expire-r64"

# 券在应用时仍有效（模板口径），应用后才把库存行改写为已过期。
VALID_UNTIL_AT_APPLY = "2026-12-31"
EXPIRED_BEFORE_PAY = "2026-09-25"


class _LocalWechatPay:
    """为支付成功通知提供不触网的本地集成。"""

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
        return "2026-09-26 12:00:00"


def _build_payment_service(handle: DatabaseHandle) -> OrderPaymentRuntimeService:
    """构建真实微信支付通知运行时。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=_LocalWechatPay(),
        event_repo=OrderEventRepo(handle),
    )


def _notify_body() -> bytes:
    """构造支付成功通知外层载荷。"""
    return json.dumps(
        {
            "id": EVENT_ID,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {"kind": "refund"},
        },
        ensure_ascii=False,
    ).encode("utf-8")


def _pay_transaction() -> dict:
    """构造覆盖券后外部支付腿的支付成功通知内容。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": MCH_ID,
        "appid": APP_ID,
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-26T12:00:00+08:00",
    }


async def _notify_payment(
    service: OrderPaymentRuntimeService,
    wechat: _LocalWechatPay,
) -> tuple[str, str]:
    """执行真实支付成功通知入口并区分业务结果与锁失败。"""
    import sqlite3

    wechat.current = _pay_transaction()
    try:
        result = await service.handle_wechat_payment_notify(
            raw_body=_notify_body(),
            headers={},
        )
        return "ok", str(result.get("status", ""))
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _seed_order_with_coupon(
    connection: aiosqlite.Connection,
) -> None:
    """写入会员、有效期未到的券，并把券应用到订单上。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '券过期会员', 'high', 1)",
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
        (MOBILE, 0),
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
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=TEMPLATE_ID,
            name="券过期测试券",
            coupon_type=CouponType.FULL_REDUCTION,
            threshold_fen=3_000,
            value_fen=COUPON_FEN,
            valid_from="2026-08-01",
            valid_until=VALID_UNTIL_AT_APPLY,
        )
    )
    await CouponInventoryRepo(connection).insert(
        CouponInventoryEntry(
            coupon_id=COUPON_ID,
            status=CouponStatus.TAKE,
            mobile=MOBILE,
            coupon_group_id=TEMPLATE_ID,
            title="券过期测试券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id=TEMPLATE_ID,
            valid_from="2026-08-01",
            valid_until=VALID_UNTIL_AT_APPLY,
        )
    )
    await connection.commit()

    coupon_service = _build_coupon_service(DatabaseHandle(connection))
    await coupon_service.apply_coupon(
        ORDER_ID,
        user_id=USER_ID,
        coupon_id=COUPON_ID,
    )
    await connection.commit()


async def _expire_coupon_before_payment(connection: aiosqlite.Connection) -> None:
    """模拟时间推进：券在应用后、支付前跨过有效期。"""
    await connection.execute(
        "UPDATE coupon_inventory SET valid_until = ? WHERE coupon_id = ?",
        (EXPIRED_BEFORE_PAY, COUPON_ID),
    )
    await connection.commit()


async def _read_state(connection: aiosqlite.Connection) -> dict[str, list[dict]]:
    """读取订单、券流水与交易认领的最终事实。"""
    queries = {
        "order": (
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        ),
        "coupons": (
            "SELECT status, order_no, deducted_fen FROM coupon_inventory "
            "WHERE coupon_id = ? ORDER BY id",
            (COUPON_ID,),
        ),
        "transactions": (
            "SELECT transaction_id, order_id FROM payment_transactions "
            "WHERE transaction_id = ?",
            (TRANSACTION_ID,),
        ),
    }
    return {
        name: await connection.execute_fetchall(sql, parameters)
        for name, (sql, parameters) in queries.items()
    }


@pytest.mark.asyncio
async def test_coupon_expiring_after_apply_must_not_strand_arrived_payment(
    tmp_path,
) -> None:
    """券在应用后过期时，已到账的微信支付不得被核销守卫整笔回滚成未支付。"""
    database_path = tmp_path / "coupon-expire-r64.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    previous_mch = settings.WECHAT_PAY_MCH_ID
    previous_app = settings.WECHAT_MINIAPP_APP_ID
    try:
        settings.WECHAT_PAY_MCH_ID = MCH_ID
        settings.WECHAT_MINIAPP_APP_ID = APP_ID
        await _seed_order_with_coupon(connection)
        wechat = _LocalWechatPay()
        service = OrderPaymentRuntimeService(
            order_repo=OrderRepo(handle),
            wechat_pay_service=wechat,
            event_repo=OrderEventRepo(handle),
        )

        await _expire_coupon_before_payment(connection)
        pay = await _notify_payment(service, wechat)
        state = await _read_state(connection)

        # 关键断言：微信资金已到账，订单必须落为已支付且认领交易号，
        # 绝不能被券核销守卫回滚成未支付而永久搁浅。
        assert pay[0] == "ok"
        assert len(state["order"]) == 1
        order = state["order"][0]
        payment = json.loads(str(order["payment"]))
        assert str(order["status"]) == OrderStatus.PENDING.value
        assert payment["status"] == "paid"
        assert payment["transactionId"] == TRANSACTION_ID
        assert int(payment["couponFen"]) == COUPON_FEN
        assert int(payment["remainFen"]) == EXTERNAL_FEN
        assert [dict(row) for row in state["transactions"]] == [
            {"transaction_id": TRANSACTION_ID, "order_id": ORDER_ID}
        ]
        # 已锁定的抵扣必须真实核销，券记为已消耗而不是留在可用态。
        assert [dict(row) for row in state["coupons"]] == [
            {"status": CouponStatus.TAKE, "order_no": "", "deducted_fen": 0},
            {
                "status": CouponStatus.CONSUME,
                "order_no": ORDER_ID,
                "deducted_fen": COUPON_FEN,
            },
        ]
    finally:
        settings.WECHAT_PAY_MCH_ID = previous_mch
        settings.WECHAT_MINIAPP_APP_ID = previous_app
        await connection.close()
