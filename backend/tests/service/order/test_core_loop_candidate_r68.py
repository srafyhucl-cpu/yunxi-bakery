"""MiniApp 核心闭环 r68：有赞权威侧核销与小程序支付竞争的收敛复核。

复核对象：`CouponInventoryService.consume_once` / `refund_once` 对
「**外部来源**（webhook / import）已核销同一张券」的处置分支。

原怀疑（r68 首版，已确认为真）：`consume_once` 只有两种语义——最新态
`CONSUME` 且 `order_no` 与本单一致时幂等返回，否则一律
`raise ValueError("优惠券已被其他订单核销")`。而该调用位于支付事务内的
最后一步。`COUPON_AUTHORITY=youzan` 是默认值，有赞是券权威来源，其
`COUPON_CUSTOMER_PROMOTION`(status=CONSUME) webhook 可以在「小程序已应用券
快照」到「微信支付成功通知到达」这个窗口内到达——此时本地最新态变成
`source=webhook` 的 `CONSUME`，`order_no` 是有赞侧订单号，与本单不匹配，
于是抛错把已真实到账的微信支付整体回滚。收件箱按 `MAX_INBOX_ATTEMPTS`
重试耗尽后进入 `dead_letter`（不再自动认领），`reconcile_pay_from_query`
在生产代码中无调用方，30 分钟超时扫描又远晚于 75 秒重试窗口，形成
「已到账收款被搁浅且无法自动收敛」的资金搁浅。

本轮结论与修复边界：

1. **外部核销不得回滚已到账支付。** 平台不是该券的权威方，无权否认外部
    已核销的事实；但也**不得**在本地再插一条 CONSUME（那会让一张券抵扣两单）。
    正确处置是：不核销、不抛错、开一条 `coupon_reconcile_case` 案件如实记录
    被争议的 `deducted_fen`，让已到账收款落账。平台按案件吸收或追偿
    `deducted_fen`——这是有界、可对账的损失，优于让 9,000 分真实到账资金
    永久失账。
2. **本地跨单核销仍然必须阻断**（r63 已定稿契约，不在本次修复范围）：
    两个 Platform 订单各持一份快照、先到者核销成功时，后到者是平台自身的
    双花尝试，平台是权威方可以拒付；改这一支会重新打开 r63 关闭的资产双花
    缺陷。两支的分野是「冲突的 CONSUME 是否归属本地」。
3. **修复让退款腿第一次可达。** 订单带着 `couponId` 落为已支付、但本地从未
    核销过该券时，全额退款若沿用旧逻辑会在外部 CONSUME 之上写一条本单的
    BACK 行，把有赞侧已消耗的券重新放回可用池。`refund_once` 因此必须补
    同一条归属守卫：只有本单真正核销过的券才允许写 BACK。

本文件用真实入口验证：券快照 → 有赞 webhook 核销 → 微信支付成功通知，
以及随后的全额退款。
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
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.youzan.event_member import handle_member_event
from tests.service.order.test_core_loop_candidate_r41 import (
    _build_coupon_service,
)

MOBILE = "13800003068"
OPENID = "coupon_youzan_race_r68_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_coupon_youzan_race_r68_001"
COUPON_ID = "coupon_youzan_race_r68_001"
TEMPLATE_ID = "template_coupon_youzan_race_r68_001"
YOUZAN_ORDER_NO = "E20260926123456789"  # pragma: allowlist secret
ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 1_000
EXTERNAL_FEN = ORDER_AMOUNT_FEN - COUPON_FEN
TRANSACTION_ID = "4200000000202609266800000001"
PAY_EVENT_ID = "EV-coupon-youzan-race-r68-pay"
REFUND_EVENT_ID = "EV-coupon-youzan-race-r68-refund"
REFUND_ID = "refund-coupon-youzan-race-r68-001"
OUT_REFUND_NO = "R-coupon-youzan-race-r68-001"
MCH_ID = "mch-coupon-youzan-race-r68"
APP_ID = "appid-coupon-youzan-race-r68"
RECONCILE_REASON = "external_consume_conflict"


class _LocalWechatPay:
    """为支付/退款成功通知提供不触网的本地集成。"""

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
        return "2026-09-26 18:00:00"


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


def _pay_transaction() -> dict:
    """构造覆盖券后外部支付腿的支付成功事实。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": MCH_ID,
        "appid": APP_ID,
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-26T18:00:00+08:00",
    }


def _refund_transaction() -> dict:
    """构造与外部支付腿完全匹配的全额退款成功事实。"""
    return {
        "mchid": MCH_ID,
        "out_trade_no": ORDER_ID,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": OUT_REFUND_NO,
        "refund_id": REFUND_ID,
        "refund_status": "SUCCESS",
        "success_time": "2026-09-26T19:00:00+08:00",
        "amount": {
            "total": EXTERNAL_FEN,
            "refund": EXTERNAL_FEN,
            "payer_total": EXTERNAL_FEN,
            "payer_refund": EXTERNAL_FEN,
        },
    }


async def _seed_member_and_order(connection: aiosqlite.Connection) -> None:
    """写入会员身份链、储值账户行和待支付订单。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '券竞争会员', 'high', 1)",
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
        "INSERT INTO member_balance (mobile, stored_value_fen, points) VALUES (?, 0, 0)",
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
            name="券竞争测试券",
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
            title="券竞争测试券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id=TEMPLATE_ID,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()


async def _deliver_youzan_consume_event(connection: aiosqlite.Connection) -> None:
    """用真实有赞会员域 webhook 入口写入一张已被有赞侧核销的券。"""
    await handle_member_event(
        connection,
        None,
        "COUPON_CUSTOMER_PROMOTION",
        {
            "id": COUPON_ID,
            "status": "CONSUME",
            "mobile": MOBILE,
            "coupon_group_id": TEMPLATE_ID,
            "order_no": YOUZAN_ORDER_NO,
        },
        "2026-09-26 17:00:00",
    )
    await connection.commit()


def _build_runtime_service(
    handle: DatabaseHandle, wechat: _LocalWechatPay
) -> OrderPaymentRuntimeService:
    """构建真实微信通知入口。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=wechat,
        event_repo=OrderEventRepo(handle),
    )


async def _read_coupon_rows(connection: aiosqlite.Connection) -> list[dict]:
    """读取该券的生命周期状态行。"""
    return await connection.execute_fetchall(
        "SELECT status, order_no, source, deducted_fen FROM coupon_inventory "
        "WHERE coupon_id = ? ORDER BY id",
        (COUPON_ID,),
    )


async def _read_reconcile_cases(connection: aiosqlite.Connection) -> list[dict]:
    """读取本单开出的券对账案件。"""
    return await connection.execute_fetchall(
        "SELECT case_key, coupon_id, order_id, external_order_no, external_source, "
        "reason, deducted_fen, status FROM coupon_reconcile_case "
        "WHERE order_id = ? ORDER BY id",
        (ORDER_ID,),
    )


async def _read_payment(connection: aiosqlite.Connection) -> dict:
    """读取订单支付快照。"""
    rows = await connection.execute_fetchall(
        "SELECT status, payment FROM orders WHERE id = ?", (ORDER_ID,)
    )
    return {
        "order_status": str(rows[0]["status"]),
        "payment": json.loads(str(rows[0]["payment"])),
    }


async def _deliver_payment_notify(
    service: OrderPaymentRuntimeService, wechat: _LocalWechatPay
) -> dict:
    """投递一次微信支付成功通知。"""
    wechat.current = _pay_transaction()
    return await service.handle_wechat_payment_notify(
        raw_body=_notify_body(PAY_EVENT_ID), headers={}
    )


@pytest.mark.asyncio
async def test_arrived_payment_lands_when_coupon_was_consumed_externally(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有赞权威侧核销同一张券后，已到账的微信支付必须落单并开对账案件。"""
    database_path = tmp_path / "coupon-youzan-race-r68.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        monkeypatch.setattr(settings, "COUPON_AUTHORITY", "youzan")
        monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", True)
        await _seed_member_and_order(connection)
        await _seed_coupon(connection)

        # 1. 用户在小程序应用券：只写支付快照，券库存仍是 TAKE。
        coupon_service = _build_coupon_service(handle)
        applied = await coupon_service.apply_coupon(
            ORDER_ID, user_id=USER_ID, coupon_id=COUPON_ID
        )
        await handle.commit()
        assert int(applied["couponFen"]) == COUPON_FEN

        # 2. 支付完成前，有赞权威侧下发 CONSUME（用户在有赞店铺用了同一张券）。
        await _deliver_youzan_consume_event(connection)
        latest = await CouponInventoryRepo(handle).get_latest_state(
            COUPON_ID, MOBILE, authority="youzan"
        )
        assert latest is not None
        assert latest["status"] == CouponStatus.CONSUME
        assert str(latest["source"]) == LedgerSource.WEBHOOK
        assert str(latest["order_no"]) == YOUZAN_ORDER_NO

        # 3. 微信支付成功通知到达：钱已到账，订单必须落为已支付。
        service = _build_runtime_service(handle, _LocalWechatPay())
        await _deliver_payment_notify(service, service._wechat_pay_service)
        await handle.commit()

        state = await _read_payment(connection)
        payment = state["payment"]
        # 关键断言一：已到账收款必须落账，且交易号被本单认领。
        assert payment["status"] == "paid"
        assert payment["transactionId"] == TRANSACTION_ID
        assert state["order_status"] == OrderStatus.PENDING.value
        transactions = await connection.execute_fetchall(
            "SELECT transaction_id, order_id FROM payment_transactions "
            "WHERE transaction_id = ?",
            (TRANSACTION_ID,),
        )
        assert [dict(row) for row in transactions] == [
            {"transaction_id": TRANSACTION_ID, "order_id": ORDER_ID}
        ]
        # 关键断言二：收件箱一次成功，不进入 failed / dead_letter 重试耗尽态。
        inbox = await connection.execute_fetchall(
            "SELECT status, attempt_count, last_error FROM inbox_events "
            "WHERE message_key = ?",
            (f"wechat_pay_notify:{PAY_EVENT_ID}",),
        )
        assert [dict(row) for row in inbox] == [
            {"status": "processed", "attempt_count": 1, "last_error": ""}
        ]

        # 关键断言三：平台无权否认外部核销，也不得本地再核销一次（一张券两单）。
        assert [dict(row) for row in await _read_coupon_rows(connection)] == [
            {
                "status": CouponStatus.TAKE,
                "order_no": "",
                "source": "import",
                "deducted_fen": 0,
            },
            {
                "status": CouponStatus.CONSUME,
                "order_no": YOUZAN_ORDER_NO,
                "source": "webhook",
                "deducted_fen": 0,
            },
        ]
        # 关键断言四：被争议的抵扣金额必须如实留痕，形成可对账案件。
        assert [dict(row) for row in await _read_reconcile_cases(connection)] == [
            {
                "case_key": f"{RECONCILE_REASON}:{ORDER_ID}:{COUPON_ID}",
                "coupon_id": COUPON_ID,
                "order_id": ORDER_ID,
                "external_order_no": YOUZAN_ORDER_NO,
                "external_source": "webhook",
                "reason": RECONCILE_REASON,
                "deducted_fen": COUPON_FEN,
                "status": "open",
            }
        ]
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_external_consume_conflict_refund_does_not_return_coupon(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """外部核销冲突下落单，全额退款不得把有赞侧已消耗的券写回可用池。"""
    database_path = tmp_path / "coupon-youzan-race-r68-refund.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        monkeypatch.setattr(settings, "COUPON_AUTHORITY", "youzan")
        monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", True)
        await _seed_member_and_order(connection)
        await _seed_coupon(connection)

        await _build_coupon_service(handle).apply_coupon(
            ORDER_ID, user_id=USER_ID, coupon_id=COUPON_ID
        )
        await handle.commit()
        await _deliver_youzan_consume_event(connection)

        wechat = _LocalWechatPay()
        service = _build_runtime_service(handle, wechat)
        await _deliver_payment_notify(service, wechat)
        await handle.commit()

        # 支付落账后进入全额退款：钱必须退，券不得凭空回到可用池。
        wechat.current = _refund_transaction()
        refund_result = await service.handle_wechat_refund_notify(
            raw_body=_notify_body(REFUND_EVENT_ID), headers={}
        )
        await handle.commit()
        assert refund_result["kind"] == "acknowledged"

        state = await _read_payment(connection)
        assert state["payment"]["status"] == "paid"
        assert state["payment"]["refundStatus"] == "full"
        assert int(state["payment"]["refundFen"]) == EXTERNAL_FEN
        # 关键断言：本单从未核销过该券，退款腿不得替有赞侧写 BACK。
        assert [dict(row) for row in await _read_coupon_rows(connection)] == [
            {
                "status": CouponStatus.TAKE,
                "order_no": "",
                "source": "import",
                "deducted_fen": 0,
            },
            {
                "status": CouponStatus.CONSUME,
                "order_no": YOUZAN_ORDER_NO,
                "source": "webhook",
                "deducted_fen": 0,
            },
        ]
        # 关键断言：案件不因退款重复开出，仍是唯一一条 open 记录。
        assert len(await _read_reconcile_cases(connection)) == 1
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_arrived_payment_notify_is_idempotent_after_external_conflict(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """外部核销冲突已被收敛后，微信重投通知必须走重复短路而非二次开案。"""
    database_path = tmp_path / "coupon-youzan-race-r68-duplicate.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        monkeypatch.setattr(settings, "COUPON_AUTHORITY", "youzan")
        monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", True)
        await _seed_member_and_order(connection)
        await _seed_coupon(connection)

        await _build_coupon_service(handle).apply_coupon(
            ORDER_ID, user_id=USER_ID, coupon_id=COUPON_ID
        )
        await handle.commit()
        await _deliver_youzan_consume_event(connection)

        wechat = _LocalWechatPay()
        service = _build_runtime_service(handle, wechat)
        await _deliver_payment_notify(service, wechat)
        await handle.commit()

        duplicate = await _deliver_payment_notify(service, wechat)
        await handle.commit()
        assert duplicate == {"duplicate": True}

        state = await _read_payment(connection)
        assert state["payment"]["status"] == "paid"
        assert state["payment"]["transactionId"] == TRANSACTION_ID
        assert len(await _read_reconcile_cases(connection)) == 1
        assert [dict(row) for row in await _read_coupon_rows(connection)] == [
            {
                "status": CouponStatus.TAKE,
                "order_no": "",
                "source": "import",
                "deducted_fen": 0,
            },
            {
                "status": CouponStatus.CONSUME,
                "order_no": YOUZAN_ORDER_NO,
                "source": "webhook",
                "deducted_fen": 0,
            },
        ]
    finally:
        await close_db(connection)
