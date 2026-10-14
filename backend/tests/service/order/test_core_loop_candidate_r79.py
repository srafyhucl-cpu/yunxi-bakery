"""MiniApp 核心闭环 r79：有赞积分权威镜像抹掉本地发分的 P1 修复验证。

复核对象：`M-20260926-030`。r69 已确认根因是「同一张余额投影表被两种
不兼容的语义写入」：

- 外部镜像（有赞 `POINTS` webhook 与 `member_loyalty` 导入）走
  `MemberBalanceRepo.upsert_identity(points=total)`，SQL 是
  `points = CASE WHEN ? IS NOT NULL THEN ? ELSE points END`，即**绝对覆盖**；
- 本地订单发分 / 退款退返走 `PointsLedgerService.credit` →
  `credit_points`，SQL 是 `points = points + ?`，即**相对增量**。

`app/service/youzan/member_api.py` 只有 `query_points` /
`list_customer_coupons` / `get_coupon_group_detail` / `list_customer_cards`
四个查询方法，**没有积分写接口**，所以本地发放的积分永远不可能出现在有赞
侧 `total` 里。任何一次有赞积分变动都会把本地已发积分抹掉，而
`points:award:{order_id}` 流水仍在；订单随后全额退款时按原流水收回这笔
从未到账的积分，形成**流水自洽但客户净损失**的结果——按流水对账查不出
任何异常。

本文件锁定修复后的不变量：**外部镜像只表达外部变化，不触碰本地账本已经
写入的净额**。

处置口径：积分属项目承接范围（见 AGENTS.md 审核与裁决规则），不得以
「第二阶段权威切换」标签规避。r69 当时把已登记语义固化为绿色钉桩测试，
本轮按确认的 P1 修复并把这些钉桩改写为正确不变量。
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
from app.repository.points_ledger_repo import PointsLedgerRepo
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.points.ledger import PointsLedgerService
from app.service.youzan.event_member import handle_member_event

MOBILE = "13800003079"
OPENID = "points_authority_r79_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_points_authority_r79_001"
ORDER_AMOUNT_FEN = 10_000
TRANSACTION_ID = "4200000000202609267900000001"
PAY_EVENT_ID = "EV-points-authority-r79-pay"
REFUND_EVENT_ID = "EV-points-authority-r79-refund"
OUT_REFUND_NO = "R-points-authority-r79-001"
REFUND_ID = "refund-points-authority-r79-001"
MCH_ID = "mch-points-authority-r79"
APP_ID = "appid-points-authority-r79"

# 有赞侧既有积分（用户在小程序下单前就有的存量，由导入镜像进本地）。
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
    # 有赞会员同步已镜像的积分余额存量。走真实导入入口
    # `mirror_youzan_points`（r79 的外部锚点写入路径），使夹具如实表达
    # 「这 500 来自有赞侧权威总额、本地净额为 0」这一真实可达状态：
    # 直接 INSERT 只写 points 会让 `youzan_points_base` 停在默认 0，
    # 于是后续镜像把整笔余额误当成本地净额而重复累加。
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


async def _count_balance_rows(connection: aiosqlite.Connection) -> int:
    """统计该会员的积分账户行数（用于确认懒建路径真实发生）。"""
    rows = await connection.execute_fetchall(
        "SELECT COUNT(*) AS n FROM member_balance WHERE mobile = ?", (MOBILE,)
    )
    return int(rows[0]["n"]) if rows else 0


async def _seed_member_without_balance_row(connection: aiosqlite.Connection) -> None:
    """写入身份链与待支付订单，但**不**建 `member_balance` 积分账户行。

    模拟 r65 记录的真实场景：新注册会员尚未被有赞同步、未发生储值或积分
    变动，`member_balance` 行尚不存在，首次下单发分时才由 `credit_points`
    懒建。
    """
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '未建档会员', 'high', 1)",
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
    """有赞积分镜像不得抹掉本地订单已发积分。

    完整链路：本地发分 100 → 有赞 POINTS 事件把外部权威总额从 500 镜像为
    550 → 断言本地余额为 650（外部 550 + 本地 100），而不是 550。

    修复前该断言失败于 `550`：外部总额被当作本地余额的绝对值写入。
    """
    database_path = tmp_path / "points-authority-r79.db"
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
            unique_id="yz:points:r79:0001",
            occurred_at="2026-09-26 15:30:00",
        )

        # 外部总额镜像进来，但本地已发的 100 必须完好：外部 550 + 本地 100。
        assert (
            await _read_points(connection) == INITIAL_YOUZAN_POINTS + 50 + AWARD_POINTS
        )
        ledger_rows = await _read_ledger(connection)
        assert any(
            str(row["unique_id"]) == f"points:award:{ORDER_ID}"
            and int(row["amount"] or 0) == AWARD_POINTS
            for row in ledger_rows
        )
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_full_refund_after_mirror_must_not_net_lose_awarded_points(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """镜像后全额退款不得让客户净损失那笔从未被外部承认的发分。

    修复前：本地发分 100 被镜像抹掉，随后退款按 `points:award` 流水收回
    100，客户净余额从 500 掉到 450——而 award 与 clawback 两条流水金额与
    归属完全自洽，按流水对账查不出异常。

    修复后：退款收回的是本地真实发出过的 100，最终余额等于外部权威总额
    550，客户既不净损失也不多拿。
    """
    database_path = tmp_path / "points-authority-r79-refund.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        monkeypatch.setattr(settings, "POINTS_AUTHORITY", "youzan")
        monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", True)
        await _seed_member_and_order(connection)

        wechat = _LocalWechatPay()
        service = _build_service(handle, wechat)

        wechat.current = _pay_transaction()
        await service.handle_wechat_payment_notify(
            raw_body=_notify_body(PAY_EVENT_ID), headers={}
        )
        await handle.commit()

        await _deliver_youzan_points_event(
            connection,
            total=INITIAL_YOUZAN_POINTS + 50,
            unique_id="yz:points:r79:refund-0001",
            occurred_at="2026-09-26 15:30:00",
        )

        wechat.current = _refund_transaction()
        refund_result = await service.handle_wechat_refund_notify(
            raw_body=_notify_body(REFUND_EVENT_ID), headers={}
        )
        await handle.commit()
        assert refund_result["kind"] == "acknowledged"

        # 收回本地真实发过的 100 后，余额恰好等于外部权威总额 550。
        assert await _read_points(connection) == INITIAL_YOUZAN_POINTS + 50

        ledger_rows = await _read_ledger(connection)
        assert any(
            str(row["unique_id"]) == f"points:refund:{ORDER_ID}:clawback"
            and int(row["amount"] or 0) == -AWARD_POINTS
            for row in ledger_rows
        )
        orders = await connection.execute_fetchall(
            "SELECT payment FROM orders WHERE id = ?", (ORDER_ID,)
        )
        payment = json.loads(str(orders[0]["payment"]))
        assert payment["refundStatus"] == "full"
        assert int(payment["refundFen"]) == ORDER_AMOUNT_FEN
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_repeated_mirror_tracks_external_delta_and_keeps_local_net(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """多次镜像只表达外部变化，本地净额在每一次镜像后都必须完好。

    锁死「外部总额是锚点、本地账本是偏移量」这个结构：第二次镜像时外部
    总额下降到 450，本地那 100 仍必须保留，余额为 550；若实现退化成绝对
    覆盖，第二次镜像会把余额写成 450。
    """
    database_path = tmp_path / "points-authority-r79-repeat.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        monkeypatch.setattr(settings, "POINTS_AUTHORITY", "youzan")
        monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", True)
        await _seed_member_and_order(connection)

        wechat = _LocalWechatPay()
        service = _build_service(handle, wechat)
        wechat.current = _pay_transaction()
        await service.handle_wechat_payment_notify(
            raw_body=_notify_body(PAY_EVENT_ID), headers={}
        )
        await handle.commit()

        await _deliver_youzan_points_event(
            connection,
            total=INITIAL_YOUZAN_POINTS + 50,
            unique_id="yz:points:r79:repeat-0001",
            occurred_at="2026-09-26 15:30:00",
        )
        assert (
            await _read_points(connection) == INITIAL_YOUZAN_POINTS + 50 + AWARD_POINTS
        )

        # 第二次镜像：外部总额下降 100（用户在有赞店铺花掉积分）。
        await _deliver_youzan_points_event(
            connection,
            total=INITIAL_YOUZAN_POINTS - 50,
            unique_id="yz:points:r79:repeat-0002",
            occurred_at="2026-09-26 16:30:00",
        )
        # 外部 450 + 本地 100。
        assert (
            await _read_points(connection) == INITIAL_YOUZAN_POINTS - 50 + AWARD_POINTS
        )
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_mirror_must_not_resurrect_locally_deducted_points(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """镜像不得把本地已扣减的积分还回来。

    这是上一条的反向不变量：只保护「本地发分不丢」而允许「本地扣减被抹掉」
    的实现等于凭空给客户发分。这里用真实 `PointsLedgerService.deduct` 扣减
    200，再镜像外部总额，余额必须是 550 - 200 = 350。
    """
    database_path = tmp_path / "points-authority-r79-deduct.db"
    connection = await init_db(str(database_path))
    try:
        monkeypatch.setattr(settings, "POINTS_AUTHORITY", "youzan")
        monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", True)
        await _seed_member_and_order(connection)

        ledger_service = PointsLedgerService(
            balance_repo=MemberBalanceRepo(connection),
            ledger_repo=PointsLedgerRepo(connection),
        )
        await ledger_service.deduct(
            mobile=MOBILE,
            amount=200,
            biz_type="order_redeem",
            biz_id=ORDER_ID,
            unique_id=f"points:redeem:{ORDER_ID}",
            event_type="order_redeem",
        )
        await connection.commit()
        assert await _read_points(connection) == INITIAL_YOUZAN_POINTS - 200

        await _deliver_youzan_points_event(
            connection,
            total=INITIAL_YOUZAN_POINTS + 50,
            unique_id="yz:points:r79:deduct-0001",
            occurred_at="2026-09-26 15:30:00",
        )

        # 外部 550 + 本地偏移 (-200) = 350。
        assert await _read_points(connection) == INITIAL_YOUZAN_POINTS + 50 - 200
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_local_points_authority_mirror_must_not_touch_local_balance(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第二阶段 `local` 权威下，有赞 POINTS 事件只写流水镜像，不得动本地余额。

    这是权威切换工作包的验收起点：切换到 `local` 后覆盖行为必须依然消失。
    """
    database_path = tmp_path / "points-authority-r79-local.db"
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
            unique_id="yz:points:r79:local-0001",
            occurred_at="2026-09-26 15:30:00",
        )

        # `local` 权威：有赞事件只追加流水与审计镜像，不动本地余额。
        assert await _read_points(connection) == awarded_balance
        ledger_rows = await _read_ledger(connection)
        assert any(
            str(row["source"]) == "webhook"
            and str(row["unique_id"]) == "yz:points:r79:local-0001"
            for row in ledger_rows
        )
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_mirror_after_lazy_created_account_keeps_local_award(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未建档新会员先由本地发分懒建账户、再被外部镜像时，本地发分必须保留。

    这是最容易被漏掉的一条真实路径：r65 已确认「新注册会员缺少
    `member_balance` 积分账户行」会命中每个未建档新会员的首次下单，
    `credit_points` 的 `UPDATE` 影响 0 行后走 `INSERT` 懒建账户。该 `INSERT`
    不写 `youzan_points_base`，列默认值 0 表示「从未镜像过，余额全部是本地
    净额」。此后再收到有赞 `POINTS` 事件时，锚点从 0 移到外部总额，本地
    发分仍必须原样保留，而不是被当成外部值重复累加或被覆盖。
    """
    database_path = tmp_path / "points-authority-r79-lazy.db"
    connection = await init_db(str(database_path))
    handle = DatabaseHandle(connection)
    try:
        monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", MCH_ID)
        monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", APP_ID)
        monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
        monkeypatch.setattr(settings, "POINTS_AUTHORITY", "youzan")
        monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", True)
        await _seed_member_without_balance_row(connection)

        # 未建档：账户行不存在。
        assert await _count_balance_rows(connection) == 0

        wechat = _LocalWechatPay()
        service = _build_service(handle, wechat)
        wechat.current = _pay_transaction()
        await service.handle_wechat_payment_notify(
            raw_body=_notify_body(PAY_EVENT_ID), headers={}
        )
        await handle.commit()

        # 发分懒建账户行，余额 100 全部是本地净额。
        assert await _count_balance_rows(connection) == 1
        assert await _read_points(connection) == AWARD_POINTS

        # 该会员同时在有赞侧有 500 存量积分，首次镜像进来。
        await _deliver_youzan_points_event(
            connection,
            total=INITIAL_YOUZAN_POINTS,
            unique_id="yz:points:r79:lazy-0001",
            occurred_at="2026-09-26 15:30:00",
        )

        # 外部 500 + 本地 100。
        assert await _read_points(connection) == INITIAL_YOUZAN_POINTS + AWARD_POINTS
    finally:
        await close_db(connection)
