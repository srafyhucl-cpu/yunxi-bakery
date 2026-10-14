"""MiniApp 核心闭环 r67：全额退款退回的优惠券能否再次使用。

复核对象：券退回后的可复用性。

怀疑（已确认为真，`M-20260926-028`）：`_compensate_full_refund` 的券腿
`refund_coupon` 写入 `source='order'` 的 `BACK` 行后，该券永久失效——
`CouponInventoryRepo.consume` 与 `CouponPaymentService.apply_coupon_snapshot`
都要求最新态为 `TAKE`，而 `BACK` 之后再无任何回到 `TAKE` 的迁移路径（全仓唯一
写 `TAKE` 的入口是 `coupon/admin.py` 的后台发券，它生成新的 `coupon_id`，
无法复活原券）。结构性根因是 `v024_coupon_module.sql` 的
`CREATE UNIQUE INDEX idx_coupon_inventory_dedup ON coupon_inventory
(coupon_id, status, mobile)`：唯一键里含**状态**，使 `TAKE → CONSUME → BACK
→ CONSUME` 的第二个周期在数据库层不可表达。

修复口径（与同库既有约定一致，不发明新范式）：`points_ledger` 与
`balance_ledger` 用 `UNIQUE(unique_id)`，唯一键是**业务操作**（含 `order_id`）
而非状态，所以同一订单的不同补偿周期天然不冲突。券对齐到同一约定：引入
`cycle_no` 消费周期维度，唯一键改为 `(coupon_id, status, mobile, cycle_no)`；
退款腿除写 `BACK`（保留冲正事实）外，再写一条**新周期的 `TAKE`** 把可持有性
重新建立起来。

选择「退款腿补写新周期 `TAKE`」而不是「让 `BACK` 直接可消费」的理由：后者要
同时改 `apply_coupon_snapshot`、`redeem_preview` 两处 `status == TAKE` 守卫，
并让接口继续把一张**可用**券报成 `status=BACK`，与小程序券中心
`member-assets.ts` 的 `BACK → refunded` 映射矛盾（用户看到「已退回」却能下单）。
补写 `TAKE` 后最新态回到 `TAKE`，`apply_coupon` / `redeem_preview` /
`get_my_coupons` / 小程序 tab 全部无需改动，语义与展示一致。

本文件用真实入口验证：券支付核销 → 全额退款退回 → 同一张券必须能再次应用到
新订单并完成核销；以及根因层「唯一键 = 业务操作」的边界。
"""

import json
import sqlite3

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
from app.service.coupon import CouponService
from tests.service.order.test_core_loop_candidate_r41 import (
    _build_coupon_service,
)

MOBILE = "13800003067"
OPENID = "coupon_reuse_after_refund_r67_001"
USER_ID = f"wx_{OPENID}"
ORDER_A = "order_coupon_reuse_a_r67_001"
ORDER_B = "order_coupon_reuse_b_r67_001"
COUPON_ID = "coupon_reuse_after_refund_r67_001"
TEMPLATE_ID = "template_coupon_reuse_r67_001"
ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 1_000
EXTERNAL_FEN = ORDER_AMOUNT_FEN - COUPON_FEN
TRANSACTION_A = "4200000000202609266700000001"
TRANSACTION_B = "4200000000202609266700000002"
PAY_EVENT_A = "EV-coupon-reuse-r67-pay-a"
REFUND_EVENT_A = "EV-coupon-reuse-r67-refund-a"
REFUND_RETRY_A = "EV-coupon-reuse-r67-refund-a-retry"
PAY_EVENT_B = "EV-coupon-reuse-r67-pay-b"
MCH_ID = "mch-coupon-reuse-r67"
APP_ID = "appid-coupon-reuse-r67"


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
        return "2026-09-26 16:00:00"


def _build_runtime(
    handle: DatabaseHandle,
) -> tuple[OrderPaymentRuntimeService, _LocalWechatPay]:
    """构建真实微信支付与退款通知运行时。"""
    wechat = _LocalWechatPay()
    service = OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=wechat,
        event_repo=OrderEventRepo(handle),
    )
    return service, wechat


def _notify_body(event_id: str) -> bytes:
    """构造微信通知外层载荷。"""
    return json.dumps(
        {
            "id": event_id,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {"kind": "refund"},
        },
        ensure_ascii=False,
    ).encode("utf-8")


def _pay_transaction(order_id: str, transaction_id: str) -> dict:
    """构造覆盖券后外部支付腿的支付成功事实。"""
    return {
        "out_trade_no": order_id,
        "trade_state": "SUCCESS",
        "mchid": MCH_ID,
        "appid": APP_ID,
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": transaction_id,
        "success_time": "2026-09-26T16:00:00+08:00",
    }


def _refund_transaction() -> dict:
    """构造与订单 A 外部支付腿完全匹配的全额退款通知内容。"""
    return {
        "mchid": MCH_ID,
        "out_trade_no": ORDER_A,
        "transaction_id": TRANSACTION_A,
        "out_refund_no": "R-coupon-reuse-r67-a",
        "refund_id": "refund-coupon-reuse-r67-a",
        "refund_status": "SUCCESS",
        "success_time": "2026-09-26T16:30:00+08:00",
        "amount": {
            "total": EXTERNAL_FEN,
            "refund": EXTERNAL_FEN,
            "payer_total": EXTERNAL_FEN,
            "payer_refund": EXTERNAL_FEN,
        },
    }


async def _seed_member_and_orders(connection: aiosqlite.Connection) -> None:
    """写入会员身份链、储值账户行和两张待支付订单。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '券复用会员', 'high', 1)",
        (f"cm_{ORDER_A}", MOBILE),
    )
    await connection.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (f"cil_{ORDER_A}", f"cm_{ORDER_A}", OPENID, OPENID),
    )
    await connection.execute(
        "INSERT INTO member_balance (mobile, stored_value_fen, points) VALUES (?, 0, 0)",
        (MOBILE,),
    )
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id, status) "
        "VALUES (?, 'miniapp', ?, 'active')",
        (f"session_{ORDER_A}", USER_ID),
    )
    repo = OrderRepo(connection)
    for order_id in (ORDER_A, ORDER_B):
        await repo.create_order(
            Order(
                id=order_id,
                session_id=f"session_{ORDER_A}",
                channel="miniapp",
                user_id=USER_ID,
                products="[]",
                total_amount=ORDER_AMOUNT_FEN / 100,
                delivery="{}",
                payment=json.dumps(
                    build_initial_payment(now_text()), ensure_ascii=False
                ),
                status=OrderStatus.PENDING,
                remark="",
                created_at=now_text(),
                updated_at=now_text(),
            )
        )
    await connection.commit()


async def _seed_coupon(connection: aiosqlite.Connection) -> None:
    """写入一张可用的满减券模板与首周期 TAKE 库存行。"""
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=TEMPLATE_ID,
            name="券复用测试券",
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
            title="券复用测试券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id=TEMPLATE_ID,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()


async def _read_coupon_rows(connection: aiosqlite.Connection) -> list[dict]:
    """读取该券的完整生命周期事实（含消费周期）。"""
    rows = await connection.execute_fetchall(
        "SELECT status, order_no, cycle_no, deducted_fen FROM coupon_inventory "
        "WHERE coupon_id = ? ORDER BY id",
        (COUPON_ID,),
    )
    return [dict(row) for row in rows]


@pytest.mark.asyncio
async def test_refunded_coupon_can_be_reused_on_new_order(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全额退款退回的券必须能再次用于新订单，不能永久失效。"""
    database_path = tmp_path / "coupon-reuse-after-refund-r67.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        await _seed_member_and_orders(connection)
        await _seed_coupon(connection)
        coupon_service = _build_coupon_service(handle)
        service, wechat = _build_runtime(handle)

        # 第一单：应用券并完成支付，券核销进首周期。
        await coupon_service.apply_coupon(ORDER_A, user_id=USER_ID, coupon_id=COUPON_ID)
        wechat.current = _pay_transaction(ORDER_A, TRANSACTION_A)
        await service.handle_wechat_payment_notify(
            raw_body=_notify_body(PAY_EVENT_A), headers={}
        )
        await handle.commit()
        first_cycle = await _read_coupon_rows(connection)
        assert [row["status"] for row in first_cycle] == [
            CouponStatus.TAKE,
            CouponStatus.CONSUME,
        ]
        assert [row["cycle_no"] for row in first_cycle] == [0, 0]

        # 全额退款：冲正写成 BACK（保留事实），并在新周期补写 TAKE 恢复可持有。
        wechat.current = _refund_transaction()
        refund_result = await service.handle_wechat_refund_notify(
            raw_body=_notify_body(REFUND_EVENT_A), headers={}
        )
        await handle.commit()
        assert refund_result["kind"] == "acknowledged"
        after_refund = await _read_coupon_rows(connection)
        assert [row["status"] for row in after_refund] == [
            CouponStatus.TAKE,
            CouponStatus.CONSUME,
            CouponStatus.BACK,
            CouponStatus.TAKE,
        ]
        # 关键事实：最新态回到 TAKE（券可再用），且第二次持有落在新周期。
        latest = await CouponInventoryRepo(handle).get_latest_state(
            COUPON_ID, MOBILE, authority=settings.COUPON_AUTHORITY
        )
        assert latest is not None
        assert latest["status"] == CouponStatus.TAKE
        assert int(latest["cycle_no"]) == 1
        assert str(latest["order_no"]) == ORDER_A

        # 第二单：同一张券必须能再次应用。退款已把整笔权益退回用户，
        # 券若不可复用就是客户资产损失。
        applied = await coupon_service.apply_coupon(
            ORDER_B, user_id=USER_ID, coupon_id=COUPON_ID
        )
        await handle.commit()
        assert int(applied["couponFen"]) == COUPON_FEN

        wechat.current = _pay_transaction(ORDER_B, TRANSACTION_B)
        await service.handle_wechat_payment_notify(
            raw_body=_notify_body(PAY_EVENT_B), headers={}
        )
        await handle.commit()
        rows = await _read_coupon_rows(connection)
        assert [row["status"] for row in rows] == [
            CouponStatus.TAKE,
            CouponStatus.CONSUME,
            CouponStatus.BACK,
            CouponStatus.TAKE,
            CouponStatus.CONSUME,
        ]
        # 关键事实：第二次核销落在第二周期，不与首周期撞唯一键。
        assert [row["cycle_no"] for row in rows] == [0, 0, 0, 1, 1]
        assert rows[-1]["order_no"] == ORDER_B
        assert rows[-1]["deducted_fen"] == COUPON_FEN
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_repeated_full_refund_does_not_duplicate_coupon_rows(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """退款腿现在写两行，补偿腿重入不得重复补写 `TAKE`。

    刻意不通过「同一笔退款换事件 ID 重投」来测：退款事实按 `out_refund_no` 唯一，
    重投在 intake 就被判为 `duplicate`，补偿腿根本不会被再次进入，那样测到的只是
    intake 幂等、不是本腿的幂等。本测试直接重入 `refund_coupon` 这条腿，隔离并
    锁定「写两行」本身的重入行为。
    """
    database_path = tmp_path / "coupon-reuse-refund-retry-r67.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        await _seed_member_and_orders(connection)
        await _seed_coupon(connection)
        coupon_service = _build_coupon_service(handle)
        service, wechat = _build_runtime(handle)

        await coupon_service.apply_coupon(ORDER_A, user_id=USER_ID, coupon_id=COUPON_ID)
        wechat.current = _pay_transaction(ORDER_A, TRANSACTION_A)
        await service.handle_wechat_payment_notify(
            raw_body=_notify_body(PAY_EVENT_A), headers={}
        )
        await handle.commit()

        wechat.current = _refund_transaction()
        first = await service.handle_wechat_refund_notify(
            raw_body=_notify_body(REFUND_EVENT_A), headers={}
        )
        await handle.commit()
        assert first["kind"] == "acknowledged"
        after_first = await _read_coupon_rows(connection)

        # 同一笔退款的微信重投在 intake 层即被判重复，不会再进补偿腿。
        wechat.current = _refund_transaction()
        replay = await service.handle_wechat_refund_notify(
            raw_body=_notify_body(REFUND_RETRY_A), headers={}
        )
        await handle.commit()
        assert replay["kind"] == "duplicate"
        # 直接重入补偿腿：两行写入必须整体幂等。
        order = await OrderRepo(handle).get_order(ORDER_A)
        assert order is not None
        await CouponService(order_repo=OrderRepo(handle)).refund_coupon(order)
        await handle.commit()
        # 关键断言：券生命周期行数与内容完全不变，没有第二条新周期 `TAKE`。
        assert await _read_coupon_rows(connection) == after_first
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_dedup_key_scopes_same_status_to_one_use_cycle(tmp_path) -> None:
    """根因取证：唯一键已按消费周期收敛，而非按状态。

    r67 首版把「第二次核销被唯一索引拒绝」写成期望值，即把结构性缺陷固化成了
    契约。修复后正确的不变量是：**同一周期内重复进入同一状态仍被唯一键挡住**
    （幂等兜底不丢），**跨周期则各占键位**（第二个消费周期合法）。本测试锁定
    替换掉坏唯一键的那个新唯一键，而不是锁定缺陷本身。
    """
    database_path = tmp_path / "coupon-reuse-cycle-key-r67.db"
    connection = await init_db(str(database_path))
    try:
        await _seed_coupon(connection)
        repo = CouponInventoryRepo(connection)
        base = dict(
            coupon_id=COUPON_ID,
            mobile=MOBILE,
            coupon_group_id=TEMPLATE_ID,
            title="券复用测试券",
            value_fen=COUPON_FEN,
            template_id=TEMPLATE_ID,
            source=LedgerSource.ORDER,
        )
        # 首周期核销 → 退款冲正 → 第二个周期重新持有。
        await repo.insert(
            CouponInventoryEntry(
                status=CouponStatus.CONSUME,
                order_no=ORDER_A,
                occurred_at="2026-08-10 09:00:00",
                cycle_no=0,
                **base,
            )
        )
        await repo.insert(
            CouponInventoryEntry(
                status=CouponStatus.BACK,
                order_no=ORDER_A,
                occurred_at="2026-08-11 09:00:00",
                cycle_no=0,
                **base,
            )
        )
        await repo.insert(
            CouponInventoryEntry(
                status=CouponStatus.TAKE,
                order_no=ORDER_A,
                occurred_at="2026-08-11 09:00:00",
                cycle_no=1,
                **base,
            )
        )
        await connection.commit()

        # 关键断言一：第二周期的核销合法落行（这正是旧唯一键禁止的动作）。
        await repo.insert(
            CouponInventoryEntry(
                status=CouponStatus.CONSUME,
                order_no=ORDER_B,
                occurred_at="2026-08-12 09:00:00",
                cycle_no=1,
                **base,
            )
        )
        await connection.commit()

        # 关键断言二：同周期重复进入同一状态仍被唯一键挡住，幂等兜底没有丢。
        with pytest.raises(sqlite3.IntegrityError):
            await repo.insert(
                CouponInventoryEntry(
                    status=CouponStatus.CONSUME,
                    order_no=ORDER_B,
                    occurred_at="2026-08-12 10:00:00",
                    cycle_no=1,
                    **base,
                )
            )
        rows = await connection.execute_fetchall(
            "SELECT status, cycle_no FROM coupon_inventory "
            "WHERE coupon_id = ? ORDER BY id",
            (COUPON_ID,),
        )
        assert [dict(row) for row in rows] == [
            {"status": CouponStatus.TAKE, "cycle_no": 0},
            {"status": CouponStatus.CONSUME, "cycle_no": 0},
            {"status": CouponStatus.BACK, "cycle_no": 0},
            {"status": CouponStatus.TAKE, "cycle_no": 1},
            {"status": CouponStatus.CONSUME, "cycle_no": 1},
        ]
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_latest_state_prefers_higher_cycle_over_later_timestamp(
    tmp_path,
) -> None:
    """跨周期事实的时间戳倒置时，当前态必须按周期而非时间戳判定。

    `occurred_at` 来自事件自带的时间，外部事件乱序、时钟漂移或补录都可能让**更高
    周期**的事实行带着**更早**的时间戳。若 `get_latest_state` 只按时间排序，就会把
    上一周期的旧行当成当前态：客户刚用掉的券又被判成可用，下一次核销会去写一个
    同周期的 `CONSUME` 行并撞上唯一键，进而在支付事务内抛错回滚已到账收款
    （与 `M-20260926-029` 同一类资金搁浅）。周期是业务事实的因果序，时间戳只承担
    同源展示序。
    """
    database_path = tmp_path / "coupon-cycle-out-of-order-r67.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        await _seed_coupon(connection)
        repo = CouponInventoryRepo(handle)

        def _row(status: str, order_no: str, at: str, cycle_no: int):
            return CouponInventoryEntry(
                coupon_id=COUPON_ID,
                status=status,
                mobile=MOBILE,
                coupon_group_id=TEMPLATE_ID,
                title="券复用测试券",
                value_fen=COUPON_FEN,
                template_id=TEMPLATE_ID,
                source=LedgerSource.ORDER,
                order_no=order_no,
                occurred_at=at,
                cycle_no=cycle_no,
            )

        # 首周期：核销 → 退款冲正 → 新周期重新持有（时间戳 10:00）。
        await repo.insert(_row(CouponStatus.CONSUME, ORDER_A, "2026-08-10 09:00:00", 0))
        await repo.insert(_row(CouponStatus.BACK, ORDER_A, "2026-08-10 10:00:00", 0))
        await repo.insert(_row(CouponStatus.TAKE, ORDER_A, "2026-08-10 10:00:00", 1))
        # 第二周期：核销 → 退款冲正 → 新周期重新持有，但时间戳整体倒置到 08:00。
        await repo.insert(_row(CouponStatus.CONSUME, ORDER_B, "2026-08-09 09:00:00", 1))
        await repo.insert(_row(CouponStatus.BACK, ORDER_B, "2026-08-09 10:00:00", 1))
        await repo.insert(_row(CouponStatus.TAKE, ORDER_B, "2026-08-09 10:00:00", 2))
        await handle.commit()

        # 关键断言：当前态是第二周期的新持有行，而不是时间戳更晚的首周期行。
        latest = await repo.get_latest_state(
            COUPON_ID, MOBILE, authority=settings.COUPON_AUTHORITY
        )
        assert latest is not None
        assert str(latest["status"]) == CouponStatus.TAKE
        assert int(latest["cycle_no"]) == 2
        assert str(latest["order_no"]) == ORDER_B

        # 「我的券」聚合同样必须按周期收敛，不能把旧周期行当成当前态。
        listed = await repo.list_by_mobile(MOBILE, authority=settings.COUPON_AUTHORITY)
        assert len(listed) == 1
        assert int(listed[0]["cycle_no"]) == 2
    finally:
        await close_db(connection)
