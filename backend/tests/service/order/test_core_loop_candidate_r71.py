"""MiniApp 核心闭环 r71：三个候选的排除取证。

r70 修掉了 `_handle_points_event` 把不可用 `total` 折叠成 0 并写进权威余额
投影的缺陷。本轮把 r70 遗留的「`to_int` / `to_fen` 折叠语义是否在别处造成
资金危害」这一开放问题查清，并对另外两个候选做排除取证。

排除项一：`to_int` / `to_fen` 折叠语义的资金危害面
    全仓 `to_int` / `to_fen` 调用点已逐一核查：除 r70 的积分 `total` 外，
    其余落点全部是券的面额 / 门槛 / 折扣，输入折叠成 0 只会让券**变得不可用**，
    方向是安全的（不会让优惠变大）。本文件用
    `test_folded_coupon_money_must_not_create_over_generous_discount` 以
    真实规则函数锁定该安全方向。

排除项二：储值充值是否为活跃货币路径
    `RechargeService` 只有 `confirm_mock_recharge_payment`，路由层也只有
    `/mock-pay`，**没有真实微信预支付端点，也没有充值专属的微信支付通知处理**；
    且 `confirm_mock_recharge_payment` 首行即校验 `ALLOW_MOCK_PAYMENT`，生产
    配置下直接拒绝。因此真实资金无法进入储值账户，充值侧不存在可造成真实
    资金损失的活动路径。本文件用
    `test_recharge_has_no_live_payment_path_and_credits_at_most_once` 同时锁定
    「无活动支付入口」与「mock 路径不重复入账」两个事实。

排除项三：微信超额退款是否留痕
    `WechatRefundNotificationService` 在金额一致性校验通过后**先**写
    `wechat_refund_events`，再判累计是否超过实付；超过时开对账案件并把
    `refundStatus` 置 `over`，不执行三腿补偿。因此已退出的资金有据可查，
    且不会因超额而错误补偿资产。本文件用
    `test_over_refund_must_record_provider_fact_without_compensating` 锁定。

    该测试同时固化一个协议事实：单笔退款通知在归一化层就被 `refund <= total`
    拒绝，且 `total` 必须等于外部支付腿，因此**单笔通知在数学上不可能构成
    超额**；`accumulated > external_paid_fen` 分支只能由多笔部分退款的累计
    触发。测试按两笔 6,000 分退款打到 9,000 分实付订单来触达。
"""

import json

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.models.coupon import CouponTemplate, CouponType
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.models.order import Order, OrderStatus
from app.models.stored_value import RechargeStatus
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.base import DatabaseHandle
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.recharge_repo import RechargeRepo
from app.repository.wechat_refund_event_repo import WechatRefundEventRepo
from app.service.coupon.rules import calc_discount, is_coupon_available
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.stored_value.member import MemberBalanceService
from app.service.stored_value.recharge import RechargeService
from app.service.youzan.member_helpers import to_fen
from tests.service.order.test_core_loop_candidate_r41 import (
    _build_coupon_service,
)

MOBILE = "13800003071"
OPENID = "exclude_r71_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_exclude_r71_001"
COUPON_ID = "coupon_exclude_r71_001"
TEMPLATE_ID = "template_exclude_r71_001"
ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 1_000
EXTERNAL_FEN = ORDER_AMOUNT_FEN - COUPON_FEN
PARTIAL_REFUND_FEN = 6_000
ACCUMULATED_REFUND_FEN = PARTIAL_REFUND_FEN * 2
RECHARGE_FEN = 10_000
TRANSACTION_ID = "4200000000202609267100000001"
PAY_EVENT_ID = "EV-exclude-r71-pay"
REFUND_EVENT_IDS = ("EV-exclude-r71-refund-1", "EV-exclude-r71-refund-2")
OUT_REFUND_NOS = ("R-exclude-r71-001", "R-exclude-r71-002")
REFUND_IDS = ("refund-exclude-r71-001", "refund-exclude-r71-002")
MCH_ID = "mch-exclude-r71"
APP_ID = "appid-exclude-r71"


class _LocalWechatPay:
    """为支付与退款成功通知提供不触网的本地集成。"""

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
        return "2026-09-26 17:00:00"


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
    """构造券抵扣后外部支付腿的支付成功通知内容。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": MCH_ID,
        "appid": APP_ID,
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-26T17:00:00+08:00",
    }


def _partial_refund_transaction(
    out_refund_no: str,
    refund_id: str,
    success_time: str,
) -> dict:
    """构造一笔不超过原支付的部分退款通知。

    `refund <= total` 且 `total == 外部支付腿` 是归一化层硬合同，因此单笔通知
    只能走「部分退款转人工」分支；超额只能靠多笔累计产生。
    """
    return {
        "mchid": MCH_ID,
        "out_trade_no": ORDER_ID,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": out_refund_no,
        "refund_id": refund_id,
        "refund_status": "SUCCESS",
        "success_time": success_time,
        "amount": {
            "total": EXTERNAL_FEN,
            "refund": PARTIAL_REFUND_FEN,
            "payer_total": EXTERNAL_FEN,
            "payer_refund": PARTIAL_REFUND_FEN,
        },
    }


async def _seed_member_and_order(connection: aiosqlite.Connection) -> None:
    """写入会员身份链、积分账户行与待支付订单。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '排除取证会员', 'high', 1)",
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
        "INSERT INTO member_balance (mobile, points, stored_value_fen) VALUES (?, 0, 0)",
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
    """写入一张可用的满减券与 TAKE 库存行（供核销使用）。"""
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=TEMPLATE_ID,
            name="排除取证券",
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
            title="排除取证券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-01-01 09:00:00",
            template_id=TEMPLATE_ID,
            valid_from="2026-01-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()


async def _read_coupon_statuses(connection: aiosqlite.Connection) -> list[str]:
    """读取排除取证券的生命周期状态序列。"""
    rows = await connection.execute_fetchall(
        "SELECT status FROM coupon_inventory WHERE coupon_id = ? ORDER BY id",
        (COUPON_ID,),
    )
    return [str(row["status"]) for row in rows]


async def _read_stored_value(connection: aiosqlite.Connection) -> int:
    """读取本地储值余额。"""
    rows = await connection.execute_fetchall(
        "SELECT stored_value_fen FROM member_balance WHERE mobile = ?", (MOBILE,)
    )
    return int(rows[0]["stored_value_fen"]) if rows else 0


def _build_member_service(handle: DatabaseHandle) -> MemberBalanceService:
    """构建真实会员余额服务。"""
    return MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )


def test_folded_coupon_money_must_not_create_over_generous_discount() -> None:
    """金额解析折叠成 0 时，券只会失效，绝不会产生超额优惠。

    这是 r70 遗留开放问题「`to_fen` / `to_int` 折叠是否在别处造成资金危害」
    的可执行答案：券面额折叠成 0 → `is_coupon_available` 因 `value_fen<=0 且
    discount_bp<=0` 判定不可用；折扣券 `discount_bp` 折叠成 0 →
    `calc_discount` 返回 0。两条折叠方向都让券变得**更严**，不存在
    「折叠后优惠变大」的资金危害路径。
    """
    # 上游畸形面额：to_fen 容忍转换后折叠成 0。
    folded_value = to_fen("not-a-number")
    assert folded_value == 0

    full_reduction = {
        "status": "active",
        "coupon_type": CouponType.FULL_REDUCTION,
        "threshold_fen": 0,
        "value_fen": folded_value,
        "discount_bp": 0,
        "cap_fen": 0,
        "valid_from": "2026-01-01",
        "valid_until": "2026-12-31",
    }
    # 面额折叠为 0 的满减券：直接判定不可用，且抵扣金额为 0。
    assert is_coupon_available(full_reduction, ORDER_AMOUNT_FEN, "2026-09-26") is False
    assert calc_discount(full_reduction, ORDER_AMOUNT_FEN) == 0

    # 折扣券：discount_bp 折叠为 0 时 calc_discount 必须返回 0，
    # 而不是把 0 当成「应付比例 0」即全额免费。
    discount_coupon = {
        "status": "active",
        "coupon_type": CouponType.DISCOUNT,
        "threshold_fen": 0,
        "value_fen": 0,
        "discount_bp": 0,
        "cap_fen": 0,
        "valid_from": "2026-01-01",
        "valid_until": "2026-12-31",
    }
    assert is_coupon_available(discount_coupon, ORDER_AMOUNT_FEN, "2026-09-26") is False
    assert calc_discount(discount_coupon, ORDER_AMOUNT_FEN) == 0

    # 折叠方向确实是「更严」：同一张券在面额正常时才可用且抵扣有上限。
    healthy = dict(full_reduction, value_fen=2_000)
    assert is_coupon_available(healthy, ORDER_AMOUNT_FEN, "2026-09-26") is True
    assert calc_discount(healthy, ORDER_AMOUNT_FEN) == 2_000
    # 抵扣永不超过订单应付。
    assert calc_discount(healthy, 500) == 500


@pytest.mark.asyncio
async def test_recharge_has_no_live_payment_path_and_credits_at_most_once(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """充值无真实支付入口，且 mock 路径最多入账一次。

    两个事实合起来界定了储值充值的影响面：真实资金无法进入储值账户
    （`confirm_mock_recharge_payment` 首行即校验 `ALLOW_MOCK_PAYMENT`，
    路由层也只有 `/mock-pay`，无微信预支付端点），因此充值侧不存在可造成
    真实资金损失的活动路径；同时 mock 路径自身也必须不重复入账。
    """
    database_path = tmp_path / "recharge-r71.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        service = RechargeService(
            recharge_repo=RechargeRepo(handle),
            member_service=_build_member_service(handle),
        )

        created = await service.create_recharge(USER_ID, RECHARGE_FEN)
        recharge_id = str(created["rechargeId"])
        assert created["status"] == RechargeStatus.UNPAID

        # 生产配置下唯一的支付入口直接拒绝：真实资金无法进入储值账户。
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", False)
        with pytest.raises(ValueError, match="生产环境已禁用 mock 支付"):
            await service.confirm_mock_recharge_payment(recharge_id, user_id=USER_ID)
        assert await _read_stored_value(connection) == 0

        # 放开 mock 后：首次入账一次，重复调用幂等，不会二次入账。
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        first = await service.confirm_mock_recharge_payment(
            recharge_id, user_id=USER_ID
        )
        assert first["status"] == RechargeStatus.PAID
        assert await _read_stored_value(connection) == RECHARGE_FEN

        second = await service.confirm_mock_recharge_payment(
            recharge_id, user_id=USER_ID
        )
        assert second["status"] == RechargeStatus.PAID
        # 关键断言：重复支付确认不会二次入账。
        assert await _read_stored_value(connection) == RECHARGE_FEN

        # 储值流水也只应有一条充值记录。
        rows = await connection.execute_fetchall(
            "SELECT COUNT(*) AS count FROM balance_ledger WHERE biz_id = ?",
            (recharge_id,),
        )
        assert int(rows[0]["count"]) == 1
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_over_refund_must_record_provider_fact_without_compensating(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """微信累计超额退款必须留痕（provider 事实 + over 状态 + 对账案件），且不补偿资产。

    已退出商户账户的资金必须能在本地查到，否则对账会出现无法解释的缺口。
    同时超额场景不得触发三腿补偿（退券/退积分/退余额），否则会把资产退给
    一个并未获得该笔退款权益的订单状态。
    """
    database_path = tmp_path / "over-refund-r71.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        monkeypatch.setattr(settings, "COUPON_AUTHORITY", "youzan")
        await _seed_member_and_order(connection)
        await _seed_coupon(connection)

        # 用户在小程序应用券：券抵扣 1,000 分，外部支付腿锁定为 9,000 分。
        applied = await _build_coupon_service(handle).apply_coupon(
            ORDER_ID, user_id=USER_ID, coupon_id=COUPON_ID
        )
        await handle.commit()
        assert int(applied["couponFen"]) == COUPON_FEN

        wechat = _LocalWechatPay()
        service = OrderPaymentRuntimeService(
            order_repo=OrderRepo(handle),
            wechat_pay_service=wechat,
            event_repo=OrderEventRepo(handle),
        )

        wechat.current = _pay_transaction()
        await service.handle_wechat_payment_notify(
            raw_body=_notify_body(PAY_EVENT_ID), headers={}
        )
        await handle.commit()
        # 券在支付成功时已核销：后续「券被退回」才有业务含义。
        assert await _read_coupon_statuses(connection) == [
            CouponStatus.TAKE,
            CouponStatus.CONSUME,
        ]

        # 第一笔 6,000 分部分退款：未达实付，转人工案件，不补偿。
        wechat.current = _partial_refund_transaction(
            OUT_REFUND_NOS[0], REFUND_IDS[0], "2026-09-26T17:30:00+08:00"
        )
        first = await service.handle_wechat_refund_notify(
            raw_body=_notify_body(REFUND_EVENT_IDS[0]), headers={}
        )
        await handle.commit()
        assert first["kind"] == "acknowledged"
        assert int(first["accumulatedFen"]) == PARTIAL_REFUND_FEN

        # 第二笔再退 6,000 分：累计 12,000 > 实付 9,000，触发超额分支。
        wechat.current = _partial_refund_transaction(
            OUT_REFUND_NOS[1], REFUND_IDS[1], "2026-09-26T17:40:00+08:00"
        )
        second = await service.handle_wechat_refund_notify(
            raw_body=_notify_body(REFUND_EVENT_IDS[1]), headers={}
        )
        await handle.commit()
        assert second["kind"] == "rejected_recorded"

        # 关键断言一：provider 退款事实已落库——已退出的钱有据可查。
        events = await WechatRefundEventRepo(handle).list_transaction_ids(ORDER_ID)
        assert TRANSACTION_ID in events
        rows = await connection.execute_fetchall(
            "SELECT out_refund_no, refund_fen, payer_refund_fen, refund_status "
            "FROM wechat_refund_events WHERE order_id = ? "
            "ORDER BY created_at, out_refund_no",
            (ORDER_ID,),
        )
        assert [str(row["out_refund_no"]) for row in rows] == list(OUT_REFUND_NOS)
        assert [int(row["refund_fen"]) for row in rows] == [
            PARTIAL_REFUND_FEN,
            PARTIAL_REFUND_FEN,
        ]
        assert all(str(row["refund_status"]) == "SUCCESS" for row in rows)
        # 已退出现金总额如实记录为累计值，不被截断到实付上限。
        assert sum(int(row["payer_refund_fen"]) for row in rows) == (
            ACCUMULATED_REFUND_FEN
        )

        # 关键断言二：订单退款状态被标记为 over，累计如实记录超额金额。
        orders = await connection.execute_fetchall(
            "SELECT payment FROM orders WHERE id = ?", (ORDER_ID,)
        )
        payment = json.loads(str(orders[0]["payment"]))
        assert payment["refundStatus"] == "over"
        assert int(payment["refundFen"]) == ACCUMULATED_REFUND_FEN

        # 关键断言三：两次退款都建了对账案件，人工可追。
        cases = await connection.execute_fetchall(
            "SELECT reason FROM points_refund_reconcile WHERE order_id = ? "
            "ORDER BY created_at, id",
            (ORDER_ID,),
        )
        reasons = [str(row["reason"]) for row in cases]
        assert f"refund:partial:{OUT_REFUND_NOS[0]}" in reasons
        assert f"refund:over_refund:{OUT_REFUND_NOS[1]}" in reasons

        # 关键断言四：超额场景不执行三腿补偿——券不退回、余额不增加。
        assert await _read_coupon_statuses(connection) == [
            CouponStatus.TAKE,
            CouponStatus.CONSUME,
        ]
        assert await _read_stored_value(connection) == 0
    finally:
        await close_db(connection)
