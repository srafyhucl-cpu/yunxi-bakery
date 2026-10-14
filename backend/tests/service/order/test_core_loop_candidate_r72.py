"""MiniApp 核心闭环 r72：三个存储值/退款腿候选的排除取证。

本轮不修改任何生产代码，只对三个此前只做过静态阅读的怀疑写最小复现：

候选一：`pay_order_with_balance` 用 `order_pay:{id}`、`prepare_combined_payment`
    用 `combined_pay:{id}`，两个不同幂等键看起来允许同一订单被扣两次储值。
    本文件用真实 `StoredValueOrderPaymentService` 双向验证：支付状态守卫
    （partial+balanceFen>0 拒绝、paid 拒绝）使两条路径互斥，储值流水恒为一条。

候选二：`CouponInventoryService.refund_once` 在最新态不是 CONSUME 时
    **静默返回 None**（与 `consume_once` 显式抛错不对称）。本文件验证这种
    不对称在「退款先于支付」时是**正确**结果：券从未核销，不能写 BACK，
    客户仍持有该券；迟到支付只补记微信事实、不核销券也不发分。

候选三：全额储值支付（或券 + 全额储值）的订单外部支付腿为 0，若此时收到
    一笔「原支付金额 = 订单总额」的微信退款通知，会否把储值错误地退回。
    本文件验证：金额不一致只建对账案件，不插 provider 事实、不补偿任何腿。
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
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.wechat_refund_event_repo import WechatRefundEventRepo
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import (
    build_initial_payment,
    loads_payment,
    now_text,
    resolve_external_paid_fen,
)
from app.utils import yuan_to_fen
from tests.service.order.test_core_loop_candidate_r41 import (
    _build_coupon_service,
    _build_payment_service,
)

MOBILE = "13800003072"
OPENID = "core_loop_r72_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_core_loop_r72_001"
COUPON_ID = "coupon_core_loop_r72_001"
TEMPLATE_ID = "template_core_loop_r72_001"
ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 1_000
EXTERNAL_FEN = ORDER_AMOUNT_FEN - COUPON_FEN
INITIAL_BALANCE_FEN = 30_000
COMBINED_BALANCE_FEN = 3_000
# 候选一夹具不含券：组合支付的外部腿 = 订单全额 - 储值腿
COMBINED_REMAIN_FEN = ORDER_AMOUNT_FEN - COMBINED_BALANCE_FEN
TRANSACTION_ID = "4200000000202609267200000001"
MCH_ID = "mch-core-loop-r72"
APP_ID = "appid-core-loop-r72"
PAY_EVENT_ID = "EV-core-loop-r72-pay"
REFUND_EVENT_ID = "EV-core-loop-r72-refund"
OUT_REFUND_NO = "R-core-loop-r72-001"
REFUND_ID = "refund-core-loop-r72-001"


class _MockWechatPay:
    """微信支付未就绪的本地替身：组合支付只会拿到 mock 尾款会话。"""

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
        return "2026-09-26 19:00:00"


def _notify_body(event_id: str) -> bytes:
    """构造支付/退款通知外层载荷。"""
    return json.dumps(
        {
            "id": event_id,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {"kind": "transaction"},
        },
        ensure_ascii=False,
    ).encode("utf-8")


def _pay_transaction(total_fen: int) -> dict:
    """构造外部支付腿金额为 total_fen 的支付成功事实。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": MCH_ID,
        "appid": APP_ID,
        "amount": {"total": total_fen, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-26T19:00:00+08:00",
    }


def _refund_transaction(total_fen: int, refund_fen: int) -> dict:
    """构造原支付金额为 total_fen 的退款成功事实。"""
    return {
        "mchid": MCH_ID,
        "out_trade_no": ORDER_ID,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": OUT_REFUND_NO,
        "refund_id": REFUND_ID,
        "refund_status": "SUCCESS",
        "success_time": "2026-09-26T20:00:00+08:00",
        "amount": {
            "total": total_fen,
            "refund": refund_fen,
            "payer_total": total_fen,
            "payer_refund": refund_fen,
        },
    }


async def _seed_member_and_order(connection: aiosqlite.Connection) -> None:
    """写入会员身份链、储值账户行与待支付订单。"""
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
            payment=json.dumps(build_initial_payment(now_text()), ensure_ascii=False),
            status=OrderStatus.PENDING,
            remark="",
            created_at=now_text(),
            updated_at=now_text(),
        )
    )
    await connection.commit()


async def _seed_coupon(connection: aiosqlite.Connection) -> None:
    """写入一张可用的满减券与 TAKE 库存行。"""
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=TEMPLATE_ID,
            name="核心闭环排除券",
            coupon_type=CouponType.FULL_REDUCTION,
            threshold_fen=3_000,
            value_fen=COUPON_FEN,
            valid_from="2026-01-01",
            valid_until="2026-12-31",
        )
    )
    await CouponInventoryRepo(connection).insert(
        CouponInventoryEntry(
            coupon_id=COUPON_ID,
            status=CouponStatus.TAKE,
            mobile=MOBILE,
            coupon_group_id=TEMPLATE_ID,
            title="核心闭环排除券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-01-01 09:00:00",
            template_id=TEMPLATE_ID,
            valid_from="2026-01-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()


async def _read_stored_value(connection: aiosqlite.Connection) -> int:
    """读取本地储值余额。"""
    rows = await connection.execute_fetchall(
        "SELECT stored_value_fen FROM member_balance WHERE mobile = ?", (MOBILE,)
    )
    return int(rows[0]["stored_value_fen"]) if rows else 0


async def _read_balance_ledger(
    connection: aiosqlite.Connection,
) -> list[dict]:
    """读取本订单的储值流水。"""
    return await connection.execute_fetchall(
        "SELECT unique_id, mobile, amount_fen FROM balance_ledger "
        "WHERE biz_id = ? ORDER BY id",
        (ORDER_ID,),
    )


async def _read_coupon_rows(connection: aiosqlite.Connection) -> list[dict]:
    """读取排除券的生命周期状态行。"""
    return await connection.execute_fetchall(
        "SELECT status, order_no, deducted_fen FROM coupon_inventory "
        "WHERE coupon_id = ? ORDER BY id",
        (COUPON_ID,),
    )


async def _read_points_ledger(connection: aiosqlite.Connection) -> list[dict]:
    """读取本订单的积分流水。"""
    return await connection.execute_fetchall(
        "SELECT unique_id, amount FROM points_ledger WHERE biz_id = ? ORDER BY id",
        (ORDER_ID,),
    )


async def _read_refund_cases(connection: aiosqlite.Connection) -> list[str]:
    """读取本订单的退款对账案件原因。"""
    rows = await connection.execute_fetchall(
        "SELECT reason FROM points_refund_reconcile WHERE order_id = ? ORDER BY id",
        (ORDER_ID,),
    )
    return [str(row["reason"]) for row in rows]


def _build_runtime_service(
    handle: DatabaseHandle, wechat: _MockWechatPay
) -> OrderPaymentRuntimeService:
    """构建真实微信通知入口。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=wechat,
        event_repo=OrderEventRepo(handle),
    )


@pytest.mark.asyncio
async def test_two_stored_value_payment_paths_cannot_double_deduct(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """余额支付与组合支付的幂等键不同，但支付状态守卫使二者互斥。

    怀疑：`order_pay:{id}` 与 `combined_pay:{id}` 是两个不同幂等键，若两条
    路径都能对同一订单扣款，储值流水会出现两条扣减、余额被扣两次。
    验证：先组合支付再余额支付、先余额支付再组合支付，两个方向都必须被
    守卫拒绝，且储值流水恒为一条扣减。
    """
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
    monkeypatch.setattr(settings, "COUPON_AUTHORITY", "youzan")

    # 方向一：先组合支付（已扣 3,000 分储值），再用余额支付补齐尾款。
    forward_path = tmp_path / "stored-value-forward-r72.db"
    connection = await init_db(str(forward_path))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        service = _build_payment_service(handle)
        combined = await service.prepare_combined_payment(
            ORDER_ID,
            user_id=USER_ID,
            balance_fen=COMBINED_BALANCE_FEN,
        )
        assert combined["payment"]["status"] == "partial"
        assert int(combined["payment"]["balanceFen"]) == COMBINED_BALANCE_FEN
        assert int(combined["payment"]["remainFen"]) == COMBINED_REMAIN_FEN
        # mock 环境不写 wechatPrepayFen，但外部支付腿金额已固化。
        payment_snapshot = loads_payment(
            (
                await connection.execute_fetchall(
                    "SELECT payment FROM orders WHERE id = ?", (ORDER_ID,)
                )
            )[0]["payment"]
        )
        assert int(payment_snapshot["externalPaidFen"]) == COMBINED_REMAIN_FEN
        assert int(payment_snapshot.get("wechatPrepayFen", 0)) == 0
        assert await _read_stored_value(connection) == (
            INITIAL_BALANCE_FEN - COMBINED_BALANCE_FEN
        )

        with pytest.raises(ValueError, match="订单已部分支付"):
            await service.pay_order_with_balance(ORDER_ID, user_id=USER_ID)

        # 关键断言：储值流水只有组合支付那一条，余额没有被二次扣减。
        assert [dict(row) for row in await _read_balance_ledger(connection)] == [
            {
                "unique_id": f"combined_pay:{ORDER_ID}",
                "mobile": MOBILE,
                "amount_fen": -COMBINED_BALANCE_FEN,
            }
        ]
        assert await _read_stored_value(connection) == (
            INITIAL_BALANCE_FEN - COMBINED_BALANCE_FEN
        )
    finally:
        await close_db(connection)

    # 方向二：先全额余额支付（订单已 paid），再发起组合支付。
    reverse_path = tmp_path / "stored-value-reverse-r72.db"
    connection = await init_db(str(reverse_path))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        service = _build_payment_service(handle)
        paid = await service.pay_order_with_balance(ORDER_ID, user_id=USER_ID)
        assert paid["paymentStatus"] == "paid"
        assert int(paid["balanceFen"]) == ORDER_AMOUNT_FEN
        assert [dict(row) for row in await _read_balance_ledger(connection)] == [
            {
                "unique_id": f"order_pay:{ORDER_ID}",
                "mobile": MOBILE,
                "amount_fen": -ORDER_AMOUNT_FEN,
            }
        ]

        with pytest.raises(ValueError, match="订单已支付"):
            await service.prepare_combined_payment(
                ORDER_ID,
                user_id=USER_ID,
                balance_fen=COMBINED_BALANCE_FEN,
            )

        # 关键断言：组合支付的幂等键从未落流水，余额只被扣一次。
        assert [dict(row) for row in await _read_balance_ledger(connection)] == [
            {
                "unique_id": f"order_pay:{ORDER_ID}",
                "mobile": MOBILE,
                "amount_fen": -ORDER_AMOUNT_FEN,
            }
        ]
        assert await _read_stored_value(connection) == (
            INITIAL_BALANCE_FEN - ORDER_AMOUNT_FEN
        )
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_refund_before_payment_keeps_coupon_and_skips_settlement(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """退款先于支付时，券不能写 BACK，迟到支付也不得核销券或发分。

    这固化了 `refund_once` 与 `consume_once` 的**刻意非对称**：核销未落行必须
    抛错（否则形成免费抵扣），而券从未核销时退回必须静默无操作——否则会把
    客户仍持有的券凭空写成已退回。
    """
    database_path = tmp_path / "refund-before-payment-r72.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        monkeypatch.setattr(settings, "COUPON_AUTHORITY", "youzan")
        await _seed_member_and_order(connection)
        await _seed_coupon(connection)

        applied = await _build_coupon_service(handle).apply_coupon(
            ORDER_ID, user_id=USER_ID, coupon_id=COUPON_ID
        )
        await connection.commit()
        assert int(applied["couponFen"]) == COUPON_FEN

        wechat = _MockWechatPay()
        service = _build_runtime_service(handle, wechat)

        # 全额退款通知先到：外部支付腿 9,000 分被退满，触发三腿补偿。
        wechat.current = _refund_transaction(EXTERNAL_FEN, EXTERNAL_FEN)
        refund_result = await service.handle_wechat_refund_notify(
            raw_body=_notify_body(REFUND_EVENT_ID), headers={}
        )
        await connection.commit()
        assert refund_result["kind"] == "acknowledged"

        # 关键断言一：券从未核销，因此不得写 BACK 行——客户仍持有该券。
        assert [dict(row) for row in await _read_coupon_rows(connection)] == [
            {"status": CouponStatus.TAKE, "order_no": "", "deducted_fen": 0}
        ]
        # 关键断言二：没有积分抵扣也没有已发积分，三腿补偿不产生积分流水。
        assert await _read_points_ledger(connection) == []
        # 关键断言三：储值腿不存在，余额不得被动。
        assert await _read_balance_ledger(connection) == []
        assert await _read_stored_value(connection) == INITIAL_BALANCE_FEN

        orders = await connection.execute_fetchall(
            "SELECT payment FROM orders WHERE id = ?", (ORDER_ID,)
        )
        payment = json.loads(str(orders[0]["payment"]))
        assert payment["refundStatus"] == "full"
        assert int(payment["refundFen"]) == EXTERNAL_FEN

        # 迟到支付到达：只补记微信到账事实，不得核销券、不得发分。
        wechat.current = _pay_transaction(EXTERNAL_FEN)
        pay_result = await service.handle_wechat_payment_notify(
            raw_body=_notify_body(PAY_EVENT_ID), headers={}
        )
        await connection.commit()
        assert pay_result["status"] == OrderStatus.PENDING.value

        # 关键断言四：迟到支付后券与积分账仍然干净。
        assert [dict(row) for row in await _read_coupon_rows(connection)] == [
            {"status": CouponStatus.TAKE, "order_no": "", "deducted_fen": 0}
        ]
        assert await _read_points_ledger(connection) == []
        assert await _read_stored_value(connection) == INITIAL_BALANCE_FEN
        orders = await connection.execute_fetchall(
            "SELECT payment FROM orders WHERE id = ?", (ORDER_ID,)
        )
        payment = json.loads(str(orders[0]["payment"]))
        assert payment["status"] == "paid"
        assert payment["transactionId"] == TRANSACTION_ID
        assert payment["refundStatus"] == "full"
        assert int(await _count_payment_transactions(connection, TRANSACTION_ID)) == 1
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_balance_only_order_rejects_mismatched_refund_without_compensating(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全额储值支付的订单外部支付腿为 0，错配退款通知只建案不补偿储值。

    怀疑：纯储值（或券 + 全额储值）付清的订单没有真实微信腿，若收到一笔
    「原支付金额 = 订单总额」的退款通知，三腿补偿会把储值错误地退回一次。
    验证：`resolve_external_paid_fen` 解析为 0，金额一致性校验先失败，
    只开对账案件，既不插 provider 退款事实，也不退任何资产。
    """
    database_path = tmp_path / "balance-only-refund-r72.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        monkeypatch.setattr(settings, "COUPON_AUTHORITY", "youzan")
        await _seed_member_and_order(connection)
        await _seed_coupon(connection)

        applied = await _build_coupon_service(handle).apply_coupon(
            ORDER_ID, user_id=USER_ID, coupon_id=COUPON_ID
        )
        await connection.commit()
        assert int(applied["couponFen"]) == COUPON_FEN

        # 余下 9,000 分全部用储值付清：订单进入 paid，外部支付腿为 0。
        paid = await _build_payment_service(handle).pay_order_with_balance(
            ORDER_ID, user_id=USER_ID
        )
        await connection.commit()
        assert paid["paymentStatus"] == "paid"

        orders = await connection.execute_fetchall(
            "SELECT payment FROM orders WHERE id = ?", (ORDER_ID,)
        )
        payment = json.loads(str(orders[0]["payment"]))
        # 关键断言一：全额储值付清后不存在任何外部支付腿。
        assert "externalPaidFen" not in payment
        assert int(payment["balanceFen"]) == EXTERNAL_FEN
        assert (
            resolve_external_paid_fen(payment, yuan_to_fen(ORDER_AMOUNT_FEN / 100)) == 0
        )
        assert str(payment.get("refundStatus", "")) == ""
        # 券已在支付成功时核销，资产账本齐备。
        assert [dict(row) for row in await _read_coupon_rows(connection)] == [
            {"status": CouponStatus.TAKE, "order_no": "", "deducted_fen": 0},
            {
                "status": CouponStatus.CONSUME,
                "order_no": ORDER_ID,
                "deducted_fen": COUPON_FEN,
            },
        ]
        assert await _read_stored_value(connection) == (
            INITIAL_BALANCE_FEN - EXTERNAL_FEN
        )

        wechat = _MockWechatPay()
        service = _build_runtime_service(handle, wechat)
        # 错配退款通知：原支付金额按订单全额 10,000 分上报。
        wechat.current = _refund_transaction(ORDER_AMOUNT_FEN, ORDER_AMOUNT_FEN)
        result = await service.handle_wechat_refund_notify(
            raw_body=_notify_body(REFUND_EVENT_ID), headers={}
        )
        await connection.commit()
        assert result["kind"] == "rejected_recorded"

        # 关键断言二：provider 退款事实未落库（金额不一致，不承认这笔退款）。
        assert await WechatRefundEventRepo(handle).list_transaction_ids(ORDER_ID) == []
        # 关键断言三：只开对账案件，金额与实付腿的差额如实留痕。
        assert await _read_refund_cases(connection) == [
            f"refund:total_mismatch:{OUT_REFUND_NO}"
        ]
        # 关键断言四：三腿一律不补偿——储值不退、券不退回、积分不收回。
        assert [dict(row) for row in await _read_balance_ledger(connection)] == [
            {
                "unique_id": f"order_pay:{ORDER_ID}",
                "mobile": MOBILE,
                "amount_fen": -EXTERNAL_FEN,
            }
        ]
        assert await _read_stored_value(connection) == (
            INITIAL_BALANCE_FEN - EXTERNAL_FEN
        )
        assert [dict(row) for row in await _read_coupon_rows(connection)] == [
            {"status": CouponStatus.TAKE, "order_no": "", "deducted_fen": 0},
            {
                "status": CouponStatus.CONSUME,
                "order_no": ORDER_ID,
                "deducted_fen": COUPON_FEN,
            },
        ]
        assert await _read_points_ledger(connection) == []
        orders = await connection.execute_fetchall(
            "SELECT payment FROM orders WHERE id = ?", (ORDER_ID,)
        )
        payment = json.loads(str(orders[0]["payment"]))
        assert int(payment.get("refundFen", 0)) == 0
        assert str(payment.get("refundStatus", "")) == ""
    finally:
        await close_db(connection)


async def _count_payment_transactions(
    connection: aiosqlite.Connection, transaction_id: str
) -> int:
    """统计指定微信交易号的认领行数。"""
    rows = await connection.execute_fetchall(
        "SELECT COUNT(*) AS count FROM payment_transactions WHERE transaction_id = ?",
        (transaction_id,),
    )
    return int(rows[0]["count"])
