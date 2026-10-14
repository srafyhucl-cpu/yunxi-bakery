"""MiniApp 核心闭环 r74：主体删除对微信尾款腿的覆盖缺口与两项复核。

r73 修复了「主体删除使已扣储值失去退款凭据」，但只结算了 `balanceFen` 一条腿。
本轮继续追问：**删除前需要结清的资产腿是否只有储值一条**。

候选一（真实 P1）：订单存在在途微信预支付（`wechatPrepayFen > 0`）时，微信侧
     预下单已生效、用户随时可完成付款。此时主体删除会连带销毁订单，但预支付
     会话在微信侧**无法撤销**。用户随后完成真实付款，支付通知到达时订单已不
     存在，`mark_paid` 抛「订单不存在」，通知按 intake 重投直至 `dead_letter`：
     钱已真实到账，本地既无订单、也无交易认领、也无对账案件。
     储值腿能「结清」，微信腿不能——只能拒绝删除。

候选二（排除）：`expire_timeout_unpaid_orders` 只扫 `status='pending'`，
     被后台确认成 `confirmed` 的未支付订单永不自动关闭。验证该订单仍可由
     `cancel_unpaid_order`（`status IN ('pending','confirmed')`）人工取消，
     属可恢复，不构成不可恢复活锁。

候选三（排除）：`clear_coupon_snapshot` 在券/积分/余额清空后把 `payment.status`
     改回 `unpaid`，疑似让已取消订单回到待支付态。验证已取消订单仍被后台
     `closed` 看板与 `cancel_unpaid_order` 双重拦住，且该函数仅在存在券快照时
     才运行，不产生资金或券状态后果。
"""

import json

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
from app.service.order.payment_state import loads_payment, now_text
from app.service.privacy_lifecycle import PrivacyLifecycleService

MOBILE = "13800003074"
OPENID = "core_loop_r74_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_core_loop_r74_001"
ORDER_AMOUNT_FEN = 10_000
INITIAL_BALANCE_FEN = 30_000
MCH_ID = "mch-core-loop-r74"
APP_ID = "appid-core-loop-r74"
TRANSACTION_ID = "4200000000202609267400000001"
PAY_EVENT_ID = "EV-core-loop-r74-pay"
PREPAY_ID = "prepay-core-loop-r74-001"


class _ReadyWechatPay:
    """微信支付「已配置」替身：让预支付走真实加锁路径，不访问微信网络。"""

    def __init__(self) -> None:
        self.current: dict = {}
        self.prepay_orders: list[str] = []

    def is_ready(self) -> bool:
        return True

    async def create_jsapi_prepay(
        self, *, order_id: str, total_fen: int, description: str, payer_openid: str
    ) -> WechatPayPrepayResult:
        self.prepay_orders.append(order_id)
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


async def _seed_member_and_order(connection: aiosqlite.Connection) -> None:
    """写入会员身份链、储值账户行与未支付订单。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '核心闭环会员', 'high', 1)",
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
        "INSERT INTO member_balance (mobile, points, stored_value_fen) VALUES (?, 0, ?)",
        (MOBILE, INITIAL_BALANCE_FEN),
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
    """构造支付成功通知外层载荷。"""
    return json.dumps(
        {
            "id": event_id,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {"kind": "transaction"},
        },
        ensure_ascii=False,
    ).encode("utf-8")


NOTIFY_HEADERS = {
    "Wechatpay-Signature": "sig",
    "Wechatpay-Timestamp": "1793000000",
    "Wechatpay-Nonce": "nonce",
    "Wechatpay-Serial": "serial",
}


async def _read_reconcile_cases(connection: aiosqlite.Connection) -> list[str]:
    """读取本订单的对账案件原因。"""
    rows = await connection.execute_fetchall(
        "SELECT reason FROM points_refund_reconcile WHERE order_id = ? ORDER BY id",
        (ORDER_ID,),
    )
    return [str(row["reason"]) for row in rows]


async def _read_transaction_claims(
    connection: aiosqlite.Connection,
) -> list[str]:
    """读取本订单的微信交易号认领。"""
    rows = await connection.execute_fetchall(
        "SELECT transaction_id FROM payment_transactions WHERE order_id = ?",
        (ORDER_ID,),
    )
    return [str(row["transaction_id"]) for row in rows]


@pytest.mark.asyncio
async def test_subject_erasure_must_not_destroy_order_with_live_wechat_prepay(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """在途微信预支付的订单不得被主体删除销毁。

    怀疑：r73 只结清了 `balanceFen` 储值腿，但微信预支付会话在微信侧已生效、
    无法撤销。删除订单后用户完成真实付款，通知找不到订单，钱到账却无本地凭据。
    验证：真实 `prepare_payment` 锁定 `wechatPrepayFen` 后执行主体删除，再投递
    真实支付成功通知，断言「到账资金必须有本地凭据」——要么订单仍在且支付事实
    落账、要么已建对账案件转人工，不能既无订单又无案件。
    """
    monkeypatch.setattr(
        "app.service.order.payment_notification.settings.WECHAT_PAY_MCH_ID", MCH_ID
    )
    monkeypatch.setattr(
        "app.service.order.payment_notification.settings.WECHAT_MINIAPP_APP_ID", APP_ID
    )

    connection = await init_db(str(tmp_path / "wechat-prepay-r74.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        order_repo = OrderRepo(handle)
        wechat = _ReadyWechatPay()
        runtime = OrderPaymentRuntimeService(
            order_repo=order_repo,
            wechat_pay_service=wechat,
            event_repo=OrderEventRepo(handle),
        )

        # 前置事实：真实预支付已发起，微信侧会话生效、用户随时可付款。
        session = await runtime.prepare_payment(ORDER_ID, user_id=USER_ID)
        assert session.mode == "wechat"
        assert wechat.prepay_orders == [ORDER_ID]
        locked = loads_payment((await order_repo.get_order(ORDER_ID)).payment)
        assert int(locked["wechatPrepayFen"]) == ORDER_AMOUNT_FEN

        # 修复后主体删除应被拒绝（微信腿在途无法本地结清）；修复前会静默删除。
        with pytest.raises(ValueError, match="微信支付在途订单"):
            await PrivacyLifecycleService(PrivacyRepo(handle)).delete_subject(USER_ID)

        # 用户随后在微信侧完成付款，通知按 out_trade_no 到达。
        wechat.current = {
            "out_trade_no": ORDER_ID,
            "trade_state": "SUCCESS",
            "mchid": MCH_ID,
            "appid": APP_ID,
            "amount": {"total": ORDER_AMOUNT_FEN, "currency": "CNY"},
            "transaction_id": TRANSACTION_ID,
            "success_time": "2026-09-26T19:00:00+08:00",
        }
        await runtime.handle_wechat_payment_notify(
            raw_body=_pay_notify_body(PAY_EVENT_ID), headers=dict(NOTIFY_HEADERS)
        )

        # 关键断言：已到账资金必须有本地凭据。
        order_after = await order_repo.get_order(ORDER_ID)
        landed = (
            order_after is not None
            and str(loads_payment(order_after.payment).get("transactionId", "") or "")
            == TRANSACTION_ID
        )
        cases = await _read_reconcile_cases(connection)
        assert landed or cases, (
            f"微信已到账 {ORDER_AMOUNT_FEN} 分但本地无凭据："
            f"订单存在={order_after is not None}，"
            f"交易认领={await _read_transaction_claims(connection)}，"
            f"对账案件={cases}"
        )
        # 到账必须真的落账，而不是靠建案兜底。
        assert landed
        assert await _read_transaction_claims(connection) == [TRANSACTION_ID]
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_confirmed_unpaid_order_stays_manually_recoverable(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超时扫描漏掉 `confirmed` 未支付订单，但该订单仍可人工取消。

    怀疑：`expire_timeout_unpaid_orders` 只扫 `status='pending'`，被后台确认成
    `confirmed` 的未支付订单永不自动关闭、预占库存永不释放。验证：该订单确实
    不被自动扫描命中，但 `cancel_unpaid_order` 允许 `confirmed`，仍可人工取消
    并释放——属可恢复，不构成不可恢复活锁。
    """
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)

    connection = await init_db(str(tmp_path / "confirmed-expire-r74.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        order_repo = OrderRepo(handle)

        # 后台把未支付订单确认成 confirmed。
        await connection.execute(
            "UPDATE orders SET status = 'confirmed', updated_at = ? WHERE id = ?",
            (now_text(), ORDER_ID),
        )
        await connection.commit()

        from app.service.order.expiration import OrderExpirationService

        expiration = OrderExpirationService(
            order_repo=order_repo,
            inventory_service=None,
            timeline_service=None,
            stored_value_service=None,
        )
        # 支付快照足够老，确保若被扫描则一定超时。
        await connection.execute(
            "UPDATE orders SET payment = ? WHERE id = ?",
            (
                json.dumps(
                    {
                        "status": "unpaid",
                        "method": "",
                        "balanceFen": 0,
                        "createdAt": "2020-01-01 00:00:00",
                    },
                    ensure_ascii=False,
                ),
                ORDER_ID,
            ),
        )
        await connection.commit()

        scanned = await expiration.expire_timeout_unpaid_orders()
        assert scanned["expiredCount"] == 0
        still_open = await order_repo.get_order(ORDER_ID)
        assert still_open is not None
        assert still_open.status == OrderStatus.CONFIRMED.value

        # 关键断言：仍可人工取消，即该订单可恢复。
        cancelled = await order_repo.cancel_unpaid_order(ORDER_ID, now_text())
        assert cancelled is not None
        assert cancelled.status == OrderStatus.CANCELLED.value
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_cleared_coupon_snapshot_on_cancelled_order_stays_closed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已取消订单清券快照后改回 `unpaid`，订单仍被双重拦住。

    怀疑：`clear_coupon_snapshot` 在券/积分/余额清空后把 `payment.status` 写回
    `unpaid`，疑似让已取消订单回到待支付态、可被再次取消或再次支付。验证：
    快照确实变回 `unpaid`，但订单状态仍为 `cancelled`，`cancel_unpaid_order`
     拒绝（状态不在 `pending`/`confirmed`），后台 `closed` 看板仍能筛出它。
    """
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
    monkeypatch.setattr(settings, "COUPON_AUTHORITY", "youzan")

    connection = await init_db(str(tmp_path / "coupon-clear-r74.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        order_repo = OrderRepo(handle)
        await connection.execute(
            "UPDATE orders SET status = 'cancelled', updated_at = ? WHERE id = ?",
            (now_text(), ORDER_ID),
        )
        await connection.execute(
            "UPDATE orders SET payment = ? WHERE id = ?",
            (
                json.dumps(
                    {
                        "status": "partial",
                        "method": "combined",
                        "couponId": "coupon-r74-001",
                        "couponFen": 1_000,
                        "balanceFen": 0,
                        "pointsFen": 0,
                    },
                    ensure_ascii=False,
                ),
                ORDER_ID,
            ),
        )
        await connection.commit()

        from tests.service.order.test_core_loop_candidate_r41 import (
            _build_coupon_service,
        )

        order = await order_repo.get_order(ORDER_ID)
        await _build_coupon_service(handle).clear_applied(order)

        cleared = await order_repo.get_order(ORDER_ID)
        payment = loads_payment(cleared.payment)
        # 快照确实被改回未支付态。
        assert payment["status"] == "unpaid"
        assert payment["couponId"] == ""
        # 关键断言：订单仍被拦住——无法再次取消，且后台 closed 看板仍可筛出。
        assert cleared.status == OrderStatus.CANCELLED.value
        assert await order_repo.cancel_unpaid_order(ORDER_ID, now_text()) is None
        board = await order_repo.list_orders(board_filter="closed")
        assert [row.id for row in board] == [ORDER_ID]
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_cancelled_order_with_live_wechat_prepay_also_blocks_erasure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已取消但微信尾款仍在途的订单同样必须阻止主体删除。

    怀疑：只拦「未支付 + 在途预支付」会漏掉已取消的订单。已取消订单的迟到支付
    由 `_record_cancelled_external_payment` 记录 `refundStatus=pending`（r73 候选二
    已确认的契约路径）；订单一旦被删除，这条唯一能记录「欠客户一笔退款」的路径
    同样消失，到账资金仍然没有本地凭据。
    """
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)

    connection = await init_db(str(tmp_path / "cancelled-prepay-r74.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        await connection.execute(
            "UPDATE orders SET status = 'cancelled', payment = ?, updated_at = ? "
            "WHERE id = ?",
            (
                json.dumps(
                    {
                        "status": "partial",
                        "method": "combined",
                        "balanceFen": 0,
                        "wechatPrepayFen": ORDER_AMOUNT_FEN,
                        "externalPaidFen": ORDER_AMOUNT_FEN,
                    },
                    ensure_ascii=False,
                ),
                now_text(),
                ORDER_ID,
            ),
        )
        await connection.commit()

        # 关键断言：已取消但尾款在途的订单也必须拦住删除。
        with pytest.raises(ValueError, match="微信支付在途订单"):
            await PrivacyLifecycleService(PrivacyRepo(handle)).delete_subject(USER_ID)
        assert await OrderRepo(handle).get_order(ORDER_ID) is not None
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_settled_wechat_prepay_does_not_block_erasure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """微信尾款已到账的订单不得阻塞主体删除。

    这是拒绝式守卫自身的过度阻塞护栏：若守卫写成「只要 `wechatPrepayFen > 0`
    就永久拒绝」，用户支付完成后仍无法行使删除权，隐私权利被永久剥夺。验证：
    支付已落账（`status=paid`）后删除正常成功。

    r75 修正：本用例原先直接 `UPDATE orders SET payment=...` 造出 paid 态，
    绕过了真实支付入口，因此从未产生 `payment_transactions` 行——而真实用户
    支付后一定有该行。夹具与真实状态不一致，导致它「证明」了删除可用，实际上
    真实已支付用户会撞 `REFERENCES orders(id)` 外键。现改为走真实预支付与
    真实支付通知，让夹具状态与生产可达状态一致。
    """
    monkeypatch.setattr(
        "app.service.order.payment_notification.settings.WECHAT_PAY_MCH_ID", MCH_ID
    )
    monkeypatch.setattr(
        "app.service.order.payment_notification.settings.WECHAT_MINIAPP_APP_ID", APP_ID
    )
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)

    connection = await init_db(str(tmp_path / "settled-prepay-r74.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        wechat = _ReadyWechatPay()
        runtime = OrderPaymentRuntimeService(
            order_repo=OrderRepo(handle),
            wechat_pay_service=wechat,
            event_repo=OrderEventRepo(handle),
        )
        await runtime.prepare_payment(ORDER_ID, user_id=USER_ID)
        wechat.current = {
            "out_trade_no": ORDER_ID,
            "trade_state": "SUCCESS",
            "mchid": MCH_ID,
            "appid": APP_ID,
            "amount": {"total": ORDER_AMOUNT_FEN, "currency": "CNY"},
            "transaction_id": TRANSACTION_ID,
            "success_time": "2026-09-26T19:00:00+08:00",
        }
        await runtime.handle_wechat_payment_notify(
            raw_body=_pay_notify_body(PAY_EVENT_ID), headers=dict(NOTIFY_HEADERS)
        )
        settled = loads_payment((await OrderRepo(handle).get_order(ORDER_ID)).payment)
        assert settled["status"] == "paid"
        assert int(settled["wechatPrepayFen"]) == ORDER_AMOUNT_FEN

        # 关键断言：已到账后不再阻塞，主体删除正常完成。
        await PrivacyLifecycleService(PrivacyRepo(handle)).delete_subject(USER_ID)
        assert await OrderRepo(handle).get_order(ORDER_ID) is None
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_plain_unpaid_order_without_prepay_does_not_block_erasure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没有微信预支付的普通未支付订单不得阻塞主体删除。

    这是拒绝式守卫的**作用域**护栏：拒绝只应针对「微信侧可能到账」的订单。
    若守卫退化成「只要未支付就拒绝」，用户只要有一笔从未支付的订单（例如
    mock 支付未确认）就永久无法行使删除权。该夹具同时锁定 `wechatPrepayFen`
    过滤条件本身承重——去掉它，此用例立即转红。
    """
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)

    connection = await init_db(str(tmp_path / "plain-unpaid-r74.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        # 普通未支付订单：没有发起过微信预支付，钱不可能从微信侧到账。
        assert (
            int(
                loads_payment(
                    (await OrderRepo(handle).get_order(ORDER_ID)).payment
                ).get("wechatPrepayFen", 0)
            )
            == 0
        )

        # 关键断言：删除正常完成，不被无谓阻塞。
        await PrivacyLifecycleService(PrivacyRepo(handle)).delete_subject(USER_ID)
        assert await OrderRepo(handle).get_order(ORDER_ID) is None
    finally:
        await close_db(connection)
