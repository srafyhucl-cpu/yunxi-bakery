"""MiniApp 核心闭环 r65：会员缺少积分账户行时已到账支付的发分守卫复核。"""

import json

import aiosqlite
import pytest

from app.config import settings
from app.database import init_db
from app.models.order import Order, OrderStatus
from app.repository.base import DatabaseHandle
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment, now_text

MOBILE = "13800003065"
OPENID = "points_account_r65_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_points_account_r65_001"
ORDER_AMOUNT_FEN = 10_000
TRANSACTION_ID = "4200000000202609266500000001"
EVENT_ID = "EV-points-account-r65-pay"
MCH_ID = "mch-points-account-r65"
APP_ID = "appid-points-account-r65"
# 实付现金 10,000 分按 1 元 = 1 分向下取整发分。
EXPECTED_AWARD_POINTS = 100


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
        return "2026-09-26 13:00:00"


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
    """构造全额微信支付成功通知内容。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": MCH_ID,
        "appid": APP_ID,
        "amount": {"total": ORDER_AMOUNT_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-26T13:00:00+08:00",
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


async def _seed_member_without_points_account(
    connection: aiosqlite.Connection,
) -> None:
    """写入已注册会员与待支付订单，但故意不建 member_balance 积分账户行。

    这是新会员的合法状态：会员主档与 openid 身份链由注册链路创建，
    `member_balance` 行只由有赞会员同步、会员忠诚度导入或储值/积分
    首次变动时懒创建，纯微信支付的订单不会触发其中任何一条。
    """
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '无积分账户会员', 'high', 1)",
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


async def _read_state(connection: aiosqlite.Connection) -> dict[str, list[dict]]:
    """读取订单、交易认领、积分账户与发分事实的最终状态。"""
    queries = {
        "order": (
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        ),
        "transactions": (
            "SELECT transaction_id, order_id FROM payment_transactions "
            "WHERE transaction_id = ?",
            (TRANSACTION_ID,),
        ),
        "member_balance": (
            "SELECT mobile, points FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        ),
        "points_ledger": (
            "SELECT unique_id, amount FROM points_ledger WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
    }
    return {
        name: await connection.execute_fetchall(sql, parameters)
        for name, (sql, parameters) in queries.items()
    }


@pytest.mark.asyncio
async def test_missing_points_account_must_not_strand_arrived_payment(
    tmp_path,
) -> None:
    """会员缺少积分账户行时，已到账的微信支付不得被发分守卫回滚成未支付。"""
    database_path = tmp_path / "points-account-r65.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    previous_mch = settings.WECHAT_PAY_MCH_ID
    previous_app = settings.WECHAT_MINIAPP_APP_ID
    try:
        settings.WECHAT_PAY_MCH_ID = MCH_ID
        settings.WECHAT_MINIAPP_APP_ID = APP_ID
        await _seed_member_without_points_account(connection)
        wechat = _LocalWechatPay()
        service = OrderPaymentRuntimeService(
            order_repo=OrderRepo(handle),
            wechat_pay_service=wechat,
            event_repo=OrderEventRepo(handle),
        )

        pay = await _notify_payment(service, wechat)
        state = await _read_state(connection)

        # 关键断言：微信资金已到账且本单没有积分抵扣，缺失的积分账户行
        # 属会员福利未建档，绝不能把收款事实连坐回滚成未支付。
        assert pay[0] == "ok"
        assert len(state["order"]) == 1
        order = state["order"][0]
        payment = json.loads(str(order["payment"]))
        assert str(order["status"]) == OrderStatus.PENDING.value
        assert payment["status"] == "paid"
        assert payment["transactionId"] == TRANSACTION_ID
        assert int(payment["pointsAwarded"]) == EXPECTED_AWARD_POINTS
        assert [dict(row) for row in state["transactions"]] == [
            {"transaction_id": TRANSACTION_ID, "order_id": ORDER_ID}
        ]
        # 账户行由发分链路懒创建，积分照常入账而不是被静默丢弃。
        assert [dict(row) for row in state["member_balance"]] == [
            {"mobile": MOBILE, "points": EXPECTED_AWARD_POINTS}
        ]
        assert [dict(row) for row in state["points_ledger"]] == [
            {
                "unique_id": f"points:award:{ORDER_ID}",
                "amount": EXPECTED_AWARD_POINTS,
            }
        ]
    finally:
        settings.WECHAT_PAY_MCH_ID = previous_mch
        settings.WECHAT_MINIAPP_APP_ID = previous_app
        await connection.close()
