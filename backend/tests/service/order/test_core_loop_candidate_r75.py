"""MiniApp 核心闭环 r75：主体删除撞上 `payment_transactions` 外键的复现。

r73/r74 已把主体删除的**资产腿**处理干净（储值结清、微信在途拒绝），但两者
都只覆盖到 `delete_subject` 之前的守卫。本轮追问守卫之后真正执行删除时
会发生什么。

候选一（真实 P1）：`payment_transactions.order_id` 声明了
`REFERENCES orders(id)` 且 `PRAGMA foreign_keys = ON`，而
`PrivacyRepo.delete_subject` 只删 `orders`、从不删 `payment_transactions`。
于是**任何真实支付成功过的用户都无法行使主体删除权**：删除事务在
`DELETE FROM orders` 处抛 `FOREIGN KEY constraint failed` 并整体回滚。
这不是 r74 测试的假象——r74 的「已支付订单不阻塞删除」用例是直接
`UPDATE orders SET payment=...` 造出 paid 态的，绕过了真实支付入口，
因此从未产生 `payment_transactions` 行，恰好漏掉了这条外键。
"""

import json
from datetime import datetime

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.models.order import Order, OrderStatus
from app.repository.base import DatabaseHandle
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.privacy_repo import PrivacyRepo
from app.service.integrations.wechat_pay import WechatPayPrepayResult
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import now_text
from app.service.privacy_lifecycle import (
    PrivacyLifecycleService,
    PrivacyRetentionPolicy,
)

MOBILE = "13800003075"
OPENID = "core_loop_r75_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_core_loop_r75_001"
ORDER_AMOUNT_FEN = 10_000
MCH_ID = "mch-core-loop-r75"
APP_ID = "appid-core-loop-r75"
TRANSACTION_ID = "4200000000202609267500000001"
PAY_EVENT_ID = "EV-core-loop-r75-pay"
PREPAY_ID = "prepay-core-loop-r75-001"


class _ReadyWechatPay:
    """微信支付「已配置」替身：走真实加锁与通知解密路径，不访问微信网络。"""

    def __init__(self) -> None:
        self.current: dict = {}

    def is_ready(self) -> bool:
        return True

    async def create_jsapi_prepay(
        self, *, order_id: str, total_fen: int, description: str, payer_openid: str
    ) -> WechatPayPrepayResult:
        return WechatPayPrepayResult(prepay_id=PREPAY_ID, appid=APP_ID)

    def build_payment_params(self, prepay_id: str, *, signer=None) -> dict:
        return {"package": f"prepay_id={prepay_id}"}

    def sign_with_rsa(self, message: str) -> str:
        return f"sig:{message}"

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
        return "2026-09-26 19:00:00"


NOTIFY_HEADERS = {
    "Wechatpay-Signature": "sig",
    "Wechatpay-Timestamp": "1793000000",
    "Wechatpay-Nonce": "nonce",
    "Wechatpay-Serial": "serial",
}


async def _seed_member_and_order(
    connection: aiosqlite.Connection,
    *,
    order_id: str = ORDER_ID,
    user_id: str = USER_ID,
    openid: str = OPENID,
    mobile: str = MOBILE,
) -> None:
    """写入会员身份链、会话与一笔未支付订单。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '核心闭环会员', 'high', 1)",
        (f"cm_{order_id}", mobile),
    )
    await connection.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (f"cil_{order_id}", f"cm_{order_id}", openid, openid),
    )
    await connection.execute(
        "INSERT INTO member_balance (mobile, points, stored_value_fen) VALUES (?, 0, 0)",
        (mobile,),
    )
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id, status) "
        "VALUES (?, 'miniapp', ?, 'active')",
        (f"session_{order_id}", user_id),
    )
    await OrderRepo(connection).create_order(
        Order(
            id=order_id,
            session_id=f"session_{order_id}",
            channel="miniapp",
            user_id=user_id,
            products="[]",
            total_amount=ORDER_AMOUNT_FEN / 100,
            delivery="{}",
            payment=json.dumps(
                {"status": "unpaid", "method": "", "balanceFen": 0},
                ensure_ascii=False,
            ),
            status=OrderStatus.PENDING,
            remark="",
            created_at=now_text(),
            updated_at=now_text(),
        )
    )
    await connection.commit()


def _pay_notify_body(event_id: str) -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {"kind": "transaction"},
        },
        ensure_ascii=False,
    ).encode("utf-8")


async def _pay_order_for_real(
    connection: aiosqlite.Connection,
    handle: DatabaseHandle,
    *,
    order_id: str = ORDER_ID,
    user_id: str = USER_ID,
    transaction_id: str = TRANSACTION_ID,
    event_id: str = PAY_EVENT_ID,
) -> None:
    """走真实预支付与通知入口把订单支付成功，落出 `payment_transactions` 行。"""
    wechat = _ReadyWechatPay()
    runtime = OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=wechat,
        event_repo=OrderEventRepo(handle),
    )
    await runtime.prepare_payment(order_id, user_id=user_id)
    wechat.current = {
        "out_trade_no": order_id,
        "trade_state": "SUCCESS",
        "mchid": MCH_ID,
        "appid": APP_ID,
        "amount": {"total": ORDER_AMOUNT_FEN, "currency": "CNY"},
        "transaction_id": transaction_id,
        "success_time": "2026-09-26T19:00:00+08:00",
    }
    await runtime.handle_wechat_payment_notify(
        raw_body=_pay_notify_body(event_id), headers=dict(NOTIFY_HEADERS)
    )


@pytest.mark.asyncio
async def test_paid_user_can_still_erase_subject(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实支付成功过的用户必须仍能行使主体删除权。

    怀疑：r74 的「已支付订单不阻塞删除」用例直接 `UPDATE orders` 造 paid 态，
    绕过了真实支付入口，因此没有 `payment_transactions` 行；而真实用户支付后
    一定会有该行。`delete_subject` 从不清理它，`DELETE FROM orders` 会被
    `REFERENCES orders(id)` 外键拒绝，整个删除事务回滚——用户永久无法删除。
    验证：走真实预支付 + 真实支付通知把订单付成功（确认外键行真实存在），
    再执行主体删除，断言删除成功且交易认领一并清理。
    """
    monkeypatch.setattr(
        "app.service.order.payment_notification.settings.WECHAT_PAY_MCH_ID", MCH_ID
    )
    monkeypatch.setattr(
        "app.service.order.payment_notification.settings.WECHAT_MINIAPP_APP_ID", APP_ID
    )
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)

    connection = await init_db(str(tmp_path / "paid-erase-r75.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        await _pay_order_for_real(connection, handle)

        # 前置事实：真实支付已落账，且外键行确实存在。
        order = await OrderRepo(handle).get_order(ORDER_ID)
        assert order is not None
        claims = await connection.execute_fetchall(
            "SELECT transaction_id FROM payment_transactions WHERE order_id = ?",
            (ORDER_ID,),
        )
        assert [str(row["transaction_id"]) for row in claims] == [TRANSACTION_ID]

        # 关键断言：已支付用户仍可行使删除权（不抛外键错误）。
        await PrivacyLifecycleService(PrivacyRepo(handle)).delete_subject(USER_ID)

        assert await OrderRepo(handle).get_order(ORDER_ID) is None
        assert (
            await connection.execute_fetchall(
                "SELECT transaction_id FROM payment_transactions WHERE order_id = ?",
                (ORDER_ID,),
            )
            == []
        )
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_delivery_order_user_can_still_erase_subject(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """下过闪送单的用户也必须能行使主体删除权。

    第二张硬外键表：`delivery_orders.order_id` 同样声明
    `REFERENCES orders(id)` 且 `on_delete=NO ACTION`。只修
    `payment_transactions` 会让闪送订单的用户继续撞外键，因此两条删除语句
    都必须真正承重，不能把其中一条当成冗余。
    """
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)

    connection = await init_db(str(tmp_path / "delivery-erase-r75.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        await connection.execute(
            "INSERT INTO delivery_orders (order_id, provider, provider_order_id, "
            "status, delivery_fee_fen, pickup_address, receiver_address) "
            "VALUES (?, 'shansong', 'ps-001', 'created', 500, '门店', '顾客地址')",
            (ORDER_ID,),
        )
        await connection.commit()

        await PrivacyLifecycleService(PrivacyRepo(handle)).delete_subject(USER_ID)

        assert await OrderRepo(handle).get_order(ORDER_ID) is None
        assert (
            await connection.execute_fetchall(
                "SELECT order_id FROM delivery_orders WHERE order_id = ?",
                (ORDER_ID,),
            )
            == []
        )
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_erasure_keeps_other_users_payment_claims(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """删除本主体时不得连带清空其他用户的交易认领。

    这是修复自身引入的**过度删除护栏**。`payment_transactions` 是全仓防重复
    入账的唯一凭据：同一微信交易号被第二个订单认领时靠它拒绝。若把修复写成
    `DELETE FROM payment_transactions`（不带用户作用域），一次主体删除就会抹掉
    所有用户的认领记录，r50 修好的「交易号只能绑定一个订单」保证随之失效。
    因此删除条件必须按 `order_id IN (SELECT id FROM orders WHERE user_id = ?)` 限定。
    """
    monkeypatch.setattr(
        "app.service.order.payment_notification.settings.WECHAT_PAY_MCH_ID", MCH_ID
    )
    monkeypatch.setattr(
        "app.service.order.payment_notification.settings.WECHAT_MINIAPP_APP_ID", APP_ID
    )
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)

    other_order_id = "order_core_loop_r75_other"
    other_user_id = "wx_core_loop_r75_other"
    other_transaction_id = "4200000000202609267599999999"

    connection = await init_db(str(tmp_path / "scoped-erase-r75.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        await _seed_member_and_order(
            connection,
            order_id=other_order_id,
            user_id=other_user_id,
            openid="core_loop_r75_other",
            mobile="13800003076",
        )
        await _pay_order_for_real(connection, handle)
        await _pay_order_for_real(
            connection,
            handle,
            order_id=other_order_id,
            user_id=other_user_id,
            transaction_id=other_transaction_id,
            event_id="EV-core-loop-r75-other",
        )

        await PrivacyLifecycleService(PrivacyRepo(handle)).delete_subject(USER_ID)

        # 关键断言：他人认领必须完好，防重复入账保证不受影响。
        survivors = await connection.execute_fetchall(
            "SELECT transaction_id, order_id FROM payment_transactions"
        )
        assert [
            (str(row["transaction_id"]), str(row["order_id"])) for row in survivors
        ] == [(other_transaction_id, other_order_id)]
        assert await OrderRepo(handle).get_order(other_order_id) is not None
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_retention_purge_completes_for_paid_orders(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """隐私保留期清理必须能跑通含已支付订单的库。

    与候选一同源的第二条删除路径：`_delete_with_cutoff("orders", ...)` 同样
    `DELETE FROM orders`，而 `payment_transactions` / `delivery_orders` 两张
    硬外键子表不在清理清单里。五张表的删除在**同一个事务**内按 messages →
    profiles → retrieval_logs → address_audit → orders 顺序执行，orders 排在
    最后，因此 orders 一旦撞外键，前面四张表已删的行会一起回滚，清理任务
    永久失败且一条数据都留不下来。

    保留期为 2555 天，故当前生产尚不会触发；但这是确定性后果而非假设：
    `apply_privacy_retention.py` 是已登记的合规作业，一旦有 7 年前的
    `done`/`cancelled` 订单（已支付订单必然带 `payment_transactions` 行），
    该作业将每次都失败。修复与候选一同形：先清两张外键子表再删订单。
    """
    monkeypatch.setattr(
        "app.service.order.payment_notification.settings.WECHAT_PAY_MCH_ID", MCH_ID
    )
    monkeypatch.setattr(
        "app.service.order.payment_notification.settings.WECHAT_MINIAPP_APP_ID", APP_ID
    )
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)

    connection = await init_db(str(tmp_path / "retention-purge-r75.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        await _pay_order_for_real(connection, handle)
        await connection.execute(
            "INSERT INTO delivery_orders (order_id, provider, provider_order_id, "
            "status, delivery_fee_fen, pickup_address, receiver_address) "
            "VALUES (?, 'shansong', 'ps-retention', 'created', 500, '门店', '顾客地址')",
            (ORDER_ID,),
        )
        # 未到保留期的另一笔已支付订单：清理不得误伤其交易认领。
        recent_order_id = "order_core_loop_r75_recent"
        recent_transaction_id = "4200000000202609267500000002"
        await _seed_member_and_order(
            connection,
            order_id=recent_order_id,
            user_id="wx_core_loop_r75_recent",
            openid="core_loop_r75_recent",
            mobile="13800003077",
        )
        await _pay_order_for_real(
            connection,
            handle,
            order_id=recent_order_id,
            user_id="wx_core_loop_r75_recent",
            transaction_id=recent_transaction_id,
            event_id="EV-core-loop-r75-recent",
        )
        # 置为可被保留期清理命中的终态，并把更新时间推到保留期窗口之外。
        await connection.execute(
            "UPDATE orders SET status = 'done', updated_at = '2000-01-01 00:00:00' "
            "WHERE id = ?",
            (ORDER_ID,),
        )
        await connection.commit()

        service = PrivacyLifecycleService(PrivacyRepo(handle))
        deleted = await service.purge_expired(
            now=datetime(2026, 9, 26),
            policy=PrivacyRetentionPolicy(orders_days=30),
        )

        assert deleted["orders"] == 1
        assert await OrderRepo(handle).get_order(ORDER_ID) is None
        assert (
            await connection.execute_fetchall(
                "SELECT transaction_id FROM payment_transactions WHERE order_id = ?",
                (ORDER_ID,),
            )
            == []
        )
        assert (
            await connection.execute_fetchall(
                "SELECT order_id FROM delivery_orders WHERE order_id = ?",
                (ORDER_ID,),
            )
            == []
        )
        # 关键断言：未到期订单及其交易认领必须完好，防重复入账保证不受影响。
        assert await OrderRepo(handle).get_order(recent_order_id) is not None
        survivors = await connection.execute_fetchall(
            "SELECT transaction_id FROM payment_transactions"
        )
        assert [str(row["transaction_id"]) for row in survivors] == [
            recent_transaction_id
        ]
    finally:
        await close_db(connection)
