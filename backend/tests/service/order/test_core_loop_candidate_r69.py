"""MiniApp 核心闭环 r69：有赞积分权威覆盖本地发分的候选复核。

复核对象：`POINTS_AUTHORITY=youzan`（默认值）下，本地订单发分与有赞
`POINTS` webhook 余额镜像的相互作用。

确认：`_handle_points_event` 在 `POINTS_AUTHORITY != "local"` 时用有赞
`total` **覆盖** `member_balance.points`（`member_balance_repo.upsert_identity`
的 `points = CASE WHEN ? IS NOT NULL THEN ? ELSE points END`），而本地订单
发分走 `PointsLedgerService.credit` → `credit_points`，是
`points = points + ?` 累加。`app/service/youzan/member_api.py` 只有
`query_points` / `list_customer_coupons` / `get_coupon_group_detail` /
`list_customer_cards` 四个查询方法，**没有积分写接口**，因此本地发的积分
永远不可能进入有赞 `total`。于是下一次任意有赞 `POINTS` 事件都会抹掉本地
已发的积分，而 `points:award:{order_id}` 流水仍在。

**r79 已修复该 P1**（`M-20260926-030`）：外部镜像改走
`mirror_youzan_points` 的锚点口径，余额恒等于「外部权威锚点 + 本地账本净额」，
镜像不再抹掉本地净额。本文件原先把「被抹掉」写成期望值（把缺陷当契约），
现按 r79 修复后的正确不变量改写，并保留第二阶段 `local` 权威的验收起点。
"""

import json

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.models.order import Order, OrderStatus
from app.repository.base import DatabaseHandle
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.youzan.event_member import handle_member_event

MOBILE = "13800003069"
OPENID = "points_authority_r69_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_points_authority_r69_001"
ORDER_AMOUNT_FEN = 10_000
TRANSACTION_ID = "4200000000202609266900000001"
PAY_EVENT_ID = "EV-points-authority-r69-pay"
REFUND_EVENT_ID = "EV-points-authority-r69-refund"
OUT_REFUND_NO = "R-points-authority-r69-001"
REFUND_ID = "refund-points-authority-r69-001"
MCH_ID = "mch-points-authority-r69"
APP_ID = "appid-points-authority-r69"

# 有赞侧既有积分（用户在小程序下单前就有的存量）。
INITIAL_YOUZAN_POINTS = 500
# 实付现金 10,000 分按 1 元 = 1 分向下取整发分。
AWARD_POINTS = 100


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
        return "2026-09-26 15:00:00"


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
    """构造全额微信支付成功通知内容。"""
    return {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": MCH_ID,
        "appid": APP_ID,
        "amount": {"total": ORDER_AMOUNT_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-26T15:00:00+08:00",
    }


def _refund_transaction() -> dict:
    """构造与订单外部支付腿完全匹配的全额退款通知内容。"""
    return {
        "mchid": MCH_ID,
        "out_trade_no": ORDER_ID,
        "transaction_id": TRANSACTION_ID,
        "out_refund_no": OUT_REFUND_NO,
        "refund_id": REFUND_ID,
        "refund_status": "SUCCESS",
        "success_time": "2026-09-26T16:00:00+08:00",
        "amount": {
            "total": ORDER_AMOUNT_FEN,
            "refund": ORDER_AMOUNT_FEN,
            "payer_total": ORDER_AMOUNT_FEN,
            "payer_refund": ORDER_AMOUNT_FEN,
        },
    }


async def _seed_member_and_order(connection: aiosqlite.Connection) -> None:
    """写入会员身份链、有赞镜像积分余额行和待支付订单。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '积分权威会员', 'high', 1)",
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
    # 有赞会员同步已镜像的积分余额存量。r79：走真实导入入口写入外部锚点，
    # 使「余额来自有赞权威总额、本地净额为 0」这一状态被如实表达。
    await MemberBalanceRepo(connection).mirror_youzan_points(
        mobile=MOBILE,
        youzan_total=INITIAL_YOUZAN_POINTS,
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


async def _deliver_youzan_points_event(
    connection: aiosqlite.Connection,
    *,
    total: int,
    unique_id: str,
    occurred_at: str,
) -> None:
    """用真实有赞会员域 webhook 入口投递一条 POINTS 余额镜像事件。

    `total` 是有赞侧权威总积分。由于 `member_api.py` 没有积分写接口，
    本地订单发放的积分不可能被计入这个 `total`。
    """
    await handle_member_event(
        connection,
        None,
        "POINTS",
        {
            "unique_id": unique_id,
            "mobile": MOBILE,
            "yz_open_id": f"yz_{OPENID}",
            "amount": 50,
            "total": total,
            "event_type": "points",
        },
        occurred_at,
    )
    await connection.commit()


async def _read_points(connection: aiosqlite.Connection) -> int:
    """读取本地积分余额投影。"""
    rows = await connection.execute_fetchall(
        "SELECT points FROM member_balance WHERE mobile = ?", (MOBILE,)
    )
    return int(rows[0]["points"]) if rows else 0


async def _read_ledger(connection: aiosqlite.Connection) -> list[dict]:
    """读取该会员的积分流水（含本地发分/收回与有赞镜像）。"""
    return await connection.execute_fetchall(
        "SELECT unique_id, amount, biz_id, source FROM points_ledger "
        "WHERE mobile = ? ORDER BY id",
        (MOBILE,),
    )


def _build_service(
    handle: DatabaseHandle,
    wechat: _LocalWechatPay,
) -> OrderPaymentRuntimeService:
    """构建真实支付运行时服务。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=wechat,
        event_repo=OrderEventRepo(handle),
    )


@pytest.mark.asyncio
async def test_youzan_points_mirror_must_not_destroy_locally_awarded_points(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有赞积分镜像不得抹掉本地订单已发积分，否则退款时客户净损失该笔积分。

    完整链路：本地发分 100 → 有赞 POINTS 事件用 `total` 覆盖余额 →
    全额退款按原流水收回 100。

    **r79 修复前**：镜像把余额覆盖成 550（本地 100 被抹掉），退款再收回 100，
    客户净余额从 500 变成 450，而 `points:award:{order_id}` 与
    `points:refund:{order_id}:clawback` 两条流水金额与归属完全自洽，按流水
    对账看不出任何异常。

    **r79 修复后**：镜像保留本地净额（余额 650），退款收回真实发出过的 100，
    最终余额等于外部权威总额 550——客户既不净损失也不多拿。
    """
    database_path = tmp_path / "points-authority-r69.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        # 第一阶段默认值：有赞是积分权威来源。
        monkeypatch.setattr(settings, "POINTS_AUTHORITY", "youzan")
        monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", True)
        await _seed_member_and_order(connection)
        assert await _read_points(connection) == INITIAL_YOUZAN_POINTS

        wechat = _LocalWechatPay()
        service = _build_service(handle, wechat)

        # 1. 本地订单支付成功：按实付现金发放 100 积分。
        wechat.current = _pay_transaction()
        await service.handle_wechat_payment_notify(
            raw_body=_notify_body(PAY_EVENT_ID), headers={}
        )
        await handle.commit()
        assert await _read_points(connection) == INITIAL_YOUZAN_POINTS + AWARD_POINTS

        # 2. 有赞侧发生一次积分变动（用户在有赞店铺消费拿到积分），
        #    webhook 携带的 `total` 是有赞权威总积分，不含本地发放的 100。
        await _deliver_youzan_points_event(
            connection,
            total=INITIAL_YOUZAN_POINTS + 50,
            unique_id="yz:points:r69:0001",
            occurred_at="2026-09-26 15:30:00",
        )
        # r79：外部总额只移动锚点，本地已发的 100 原样保留（外部 550 + 本地 100）。
        assert (
            await _read_points(connection) == INITIAL_YOUZAN_POINTS + 50 + AWARD_POINTS
        )
        ledger_rows = await _read_ledger(connection)
        assert any(
            str(row["unique_id"]) == f"points:award:{ORDER_ID}"
            and int(row["amount"] or 0) == AWARD_POINTS
            for row in ledger_rows
        )

        # 3. 全额退款：按原流水收回已发积分 100。
        wechat.current = _refund_transaction()
        refund_result = await service.handle_wechat_refund_notify(
            raw_body=_notify_body(REFUND_EVENT_ID), headers={}
        )
        await handle.commit()
        assert refund_result["kind"] == "acknowledged"

        # 收回的是本地真实发出过的 100，最终余额等于外部权威总额。
        assert await _read_points(connection) == INITIAL_YOUZAN_POINTS + 50

        # 且流水层面完全自洽，按流水对账无法发现这 100 分净损失。
        ledger_rows = await _read_ledger(connection)
        assert any(
            str(row["unique_id"]) == f"points:refund:{ORDER_ID}:clawback"
            and int(row["amount"] or 0) == -AWARD_POINTS
            for row in ledger_rows
        )
        orders = await connection.execute_fetchall(
            "SELECT status, payment FROM orders WHERE id = ?", (ORDER_ID,)
        )
        # 退款事实本身完整落账（累计=实付、终态 full），
        # 说明这 100 分净损失不是退款失败造成的，而是权威覆盖造成的。
        payment = json.loads(str(orders[0]["payment"]))
        assert payment["refundStatus"] == "full"
        assert int(payment["refundFen"]) == ORDER_AMOUNT_FEN
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_local_points_authority_mirror_must_not_touch_local_balance(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第二阶段 `local` 权威下，有赞 POINTS 事件只写流水镜像，不得覆盖本地余额。

    这是 r69 权威切换工作包的验收起点：切换到 `local` 后覆盖行为必须消失，
    否则本地账本虽为唯一事实源却仍被外部 `total` 覆盖。
    """
    database_path = tmp_path / "points-authority-r69-local.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        monkeypatch.setattr(settings, "POINTS_AUTHORITY", "local")
        monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", True)
        await _seed_member_and_order(connection)

        wechat = _LocalWechatPay()
        service = _build_service(handle, wechat)
        wechat.current = _pay_transaction()
        await service.handle_wechat_payment_notify(
            raw_body=_notify_body(PAY_EVENT_ID), headers={}
        )
        await handle.commit()
        awarded_balance = await _read_points(connection)
        assert awarded_balance == INITIAL_YOUZAN_POINTS + AWARD_POINTS

        await _deliver_youzan_points_event(
            connection,
            total=INITIAL_YOUZAN_POINTS + 50,
            unique_id="yz:points:r69:local-0001",
            occurred_at="2026-09-26 15:30:00",
        )

        # `local` 权威：有赞事件只追加流水与审计镜像，不动本地余额。
        assert await _read_points(connection) == awarded_balance
        ledger_rows = await _read_ledger(connection)
        assert any(
            str(row["source"]) == "webhook"
            and str(row["unique_id"]) == "yz:points:r69:local-0001"
            for row in ledger_rows
        )
    finally:
        await close_db(connection)
