"""会员储值余额 M2 测试：充值入账 / 余额支付 / 组合支付与退款闭环。"""

import aiosqlite
import pytest

from app.config import settings

from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.config_repo import ConfigRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.recharge_repo import RechargeRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order.payment_notification import WechatPaymentNotificationService
from app.service.order import OrderApplicationService
from app.service.stored_value import (
    MemberBalanceService,
    RechargeService,
    StoredValueOrderPaymentService,
    StoredValueService,
)

MOBILE = "13800000001"
OPENID = "openid_m2_001"
USER_ID = f"wx_{OPENID}"


async def _seed_member(
    db: aiosqlite.Connection,
    *,
    openid: str = OPENID,
    mobile: str = MOBILE,
    balance_fen: int = 0,
) -> None:
    """落库客户主档 + 小程序身份链接 + 会员余额账户。"""
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '测试会员', 'high', 1)",
        (f"cm_{openid}", mobile),
    )
    await db.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (f"cil_{openid}", f"cm_{openid}", openid, openid),
    )
    if balance_fen:
        await db.execute(
            "INSERT INTO member_balance (mobile, stored_value_fen) VALUES (?, ?)",
            (mobile, balance_fen),
        )
    await db.commit()


@pytest.fixture
def stored_value_service(db: aiosqlite.Connection) -> StoredValueService:
    """使用真实内存库仓储构建储值域服务。"""
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    return StoredValueService(
        member_service=member_service,
        recharge_service=RechargeService(
            recharge_repo=RechargeRepo(db),
            member_service=member_service,
        ),
        payment_service=StoredValueOrderPaymentService(
            order_repo=OrderRepo(db),
            member_service=member_service,
        ),
    )


@pytest.fixture
def order_service(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
) -> OrderApplicationService:
    """构建订单应用服务并接入储值退款钩子。"""
    return OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
        stored_value_service=stored_value_service,
    )


async def _create_order(
    order_service: OrderApplicationService,
    *,
    price_fen: int = 5000,
    user_id: str = USER_ID,
) -> str:
    created = await order_service.create_order(
        {
            "items": [
                {
                    "productId": "p_m2_001",
                    "title": "M2 储值测试蛋糕",
                    "priceFen": price_fen,
                    "quantity": 1,
                }
            ],
            "receiverName": "储值测试",
            "receiverPhone": MOBILE,
            "deliveryType": "delivery",
            "deliveryAddress": "储值测试地址",
            "expectTime": "2026-08-20 19:00",
        },
        user_id=user_id,
    )
    return created["orderId"]


async def _balance_fen(db: aiosqlite.Connection) -> int:
    rows = await db.execute_fetchall(
        "SELECT stored_value_fen FROM member_balance WHERE mobile = ? LIMIT 1",
        (MOBILE,),
    )
    return int(rows[0]["stored_value_fen"]) if rows else 0


async def _ledger_rows(db: aiosqlite.Connection) -> list[dict]:
    return await db.execute_fetchall(
        "SELECT unique_id, amount_fen, biz_type, biz_id, balance_after_fen "
        "FROM balance_ledger WHERE mobile = ? ORDER BY id ASC",
        (MOBILE,),
    )


async def test_stored_value_tables_created(db: aiosqlite.Connection) -> None:
    """初始化数据库后应包含充值单与余额流水表及关键字段。"""
    recharge_columns = [
        row["name"]
        for row in await db.execute_fetchall("PRAGMA table_info(stored_value_recharge)")
    ]
    assert {"id", "user_id", "mobile", "amount_fen", "status"}.issubset(
        recharge_columns
    )
    ledger_columns = [
        row["name"]
        for row in await db.execute_fetchall("PRAGMA table_info(balance_ledger)")
    ]
    assert {
        "unique_id",
        "amount_fen",
        "balance_after_fen",
        "biz_type",
        "biz_id",
    }.issubset(ledger_columns)


@pytest.mark.asyncio
async def test_recharge_mock_pay_credits_balance_once(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
) -> None:
    """mock 充值应入账余额并写流水，重复确认不重复入账。"""
    await _seed_member(db)
    created = await stored_value_service.create_recharge(USER_ID, 5000)
    assert created["status"] == "unpaid"
    paid = await stored_value_service.confirm_mock_recharge_payment(
        created["rechargeId"], user_id=USER_ID
    )
    assert paid["status"] == "paid"
    assert paid["paymentMethod"] == "mock"
    assert await _balance_fen(db) == 5000
    # 重复确认幂等
    again = await stored_value_service.confirm_mock_recharge_payment(
        created["rechargeId"], user_id=USER_ID
    )
    assert again["status"] == "paid"
    assert await _balance_fen(db) == 5000
    ledger = await _ledger_rows(db)
    assert len(ledger) == 1
    assert ledger[0]["biz_type"] == "recharge"
    assert ledger[0]["amount_fen"] == 5000


@pytest.mark.asyncio
async def test_recharge_amount_bounds_and_cancel(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
) -> None:
    """充值金额上下限校验；未支付充值单可取消，已支付不可取消。"""
    await _seed_member(db)
    with pytest.raises(ValueError, match="充值金额不能低于"):
        await stored_value_service.create_recharge(USER_ID, 50)
    with pytest.raises(ValueError, match="充值金额不能超过"):
        await stored_value_service.create_recharge(USER_ID, 50_001)
    accepted = await stored_value_service.create_recharge(USER_ID, 50_000)
    assert accepted["status"] == "unpaid"
    cancelled = await stored_value_service.cancel_unpaid_recharge(
        accepted["rechargeId"], user_id=USER_ID
    )
    assert cancelled["status"] == "cancelled"
    assert await _balance_fen(db) == 0
    second = await stored_value_service.create_recharge(USER_ID, 1000)
    await stored_value_service.confirm_mock_recharge_payment(
        second["rechargeId"], user_id=USER_ID
    )
    with pytest.raises(ValueError, match="当前充值单状态不允许取消"):
        await stored_value_service.cancel_unpaid_recharge(
            second["rechargeId"], user_id=USER_ID
        )


@pytest.mark.asyncio
async def test_unrecognized_user_rejected(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
) -> None:
    """未识别为会员的用户不能充值或查询余额。"""
    with pytest.raises(ValueError, match="当前用户未识别为会员"):
        await stored_value_service.create_recharge("wx_openid_unknown", 1000)
    with pytest.raises(ValueError, match="当前用户未识别为会员"):
        await stored_value_service.get_user_balance("wx_openid_unknown")


@pytest.mark.asyncio
async def test_pay_order_with_balance_success_and_idempotent(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """全额余额支付应扣款并置订单已支付，重复支付不重复扣款。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    paid = await stored_value_service.pay_order_with_balance(order_id, user_id=USER_ID)
    assert paid["paymentStatus"] == "paid"
    assert paid["paymentMethod"] == "balance"
    assert paid["balanceFen"] == 5000
    assert await _balance_fen(db) == 95_000
    again = await stored_value_service.pay_order_with_balance(order_id, user_id=USER_ID)
    assert again["paymentStatus"] == "paid"
    assert await _balance_fen(db) == 95_000
    ledger = await _ledger_rows(db)
    assert len(ledger) == 1
    assert ledger[0]["biz_type"] == "order_pay"
    assert ledger[0]["amount_fen"] == -5000


@pytest.mark.asyncio
async def test_pay_order_with_balance_insufficient_no_deduct(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """余额不足时余额支付应拒绝且不扣款、订单保持未支付。"""
    await _seed_member(db, balance_fen=3000)
    order_id = await _create_order(order_service, price_fen=5000)
    with pytest.raises(ValueError, match="储值余额不足"):
        await stored_value_service.pay_order_with_balance(order_id, user_id=USER_ID)
    assert await _balance_fen(db) == 3000
    detail = await order_service.get_user_order(order_id, user_id=USER_ID)
    assert detail["status"] == "pending"


@pytest.mark.asyncio
async def test_combined_payment_flow_and_remainder_mock_pay(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """组合支付：扣余额部分置中间态，差额 mock 完成后订单支付。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    combined = await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    assert combined["payment"]["status"] == "partial"
    assert combined["payment"]["balanceFen"] == 2000
    assert combined["payment"]["remainFen"] == 3000
    assert combined["remainderPayment"]["paymentMethod"] == "mock"
    assert await _balance_fen(db) == 98_000
    paid = await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    assert paid["paymentStatus"] == "paid"
    assert paid["paymentMethod"] == "combined"
    assert await _balance_fen(db) == 98_000
    ledger = await _ledger_rows(db)
    assert len(ledger) == 1
    assert ledger[0]["biz_id"] == order_id
    assert ledger[0]["amount_fen"] == -2000


@pytest.mark.asyncio
async def test_combined_payment_invalid_split_rejected(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """组合支付余额部分必须大于 0 且小于订单总额。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    with pytest.raises(ValueError, match="必须大于 0 且小于订单总额"):
        await stored_value_service.prepare_combined_payment(
            order_id, user_id=USER_ID, balance_fen=5000
        )
    with pytest.raises(ValueError, match="必须大于 0 且小于订单总额"):
        await stored_value_service.prepare_combined_payment(
            order_id, user_id=USER_ID, balance_fen=0
        )
    assert await _balance_fen(db) == 100_000


@pytest.mark.asyncio
async def test_combined_payment_user_cancel_refunds_balance(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """组合支付订单取消后应原路退回已扣余额，且不重复退款。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    assert await _balance_fen(db) == 98_000
    cancelled = await order_service.cancel_user_order(order_id, user_id=USER_ID)
    assert cancelled["status"] == "cancelled"
    assert await _balance_fen(db) == 100_000
    # 重复取消不重复退款
    await order_service.cancel_user_order(order_id, user_id=USER_ID)
    assert await _balance_fen(db) == 100_000
    ledger = await _ledger_rows(db)
    assert [row["biz_type"] for row in ledger] == ["order_pay", "order_refund"]
    assert ledger[1]["amount_fen"] == 2000


@pytest.mark.asyncio
async def test_combined_payment_timeout_expire_refunds_balance(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """组合支付订单超时关闭后应原路退回已扣余额。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    assert await _balance_fen(db) == 98_000
    expired = await order_service.expire_unpaid_order(order_id)
    assert expired["status"] == "cancelled"
    assert await _balance_fen(db) == 100_000


@pytest.mark.asyncio
async def test_admin_cancel_partial_order_refunds_balance(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """后台取消组合支付订单应原路退回已扣余额。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    assert await _balance_fen(db) == 98_000
    cancelled = await order_service.update_admin_order_status(order_id, "cancelled")
    assert cancelled["status"] == "cancelled"
    assert await _balance_fen(db) == 100_000


@pytest.mark.asyncio
async def test_balance_paid_order_cannot_be_cancelled_or_refunded(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """全额余额支付后订单不可取消，已扣余额不原路退回。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.pay_order_with_balance(order_id, user_id=USER_ID)
    assert await _balance_fen(db) == 95_000
    with pytest.raises(ValueError, match="已支付订单不允许取消"):
        await order_service.cancel_user_order(order_id, user_id=USER_ID)
    with pytest.raises(ValueError, match="已支付订单不允许取消"):
        await order_service.update_admin_order_status(order_id, "cancelled")
    assert await _balance_fen(db) == 95_000
    ledger = await _ledger_rows(db)
    assert [row["biz_type"] for row in ledger] == ["order_pay"]


@pytest.mark.asyncio
async def test_combined_payment_prepare_twice_and_mock_confirm_idempotent(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
) -> None:
    """组合支付不可重复准备；差额 mock 完成后重复确认不重复扣款。"""
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    with pytest.raises(ValueError, match="订单已部分支付"):
        await stored_value_service.prepare_combined_payment(
            order_id, user_id=USER_ID, balance_fen=1000
        )
    assert await _balance_fen(db) == 98_000
    await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    again = await order_service.confirm_mock_payment(order_id, user_id=USER_ID)
    assert again["paymentStatus"] == "paid"
    assert await _balance_fen(db) == 98_000
    ledger = await _ledger_rows(db)
    assert len(ledger) == 1
    assert ledger[0]["amount_fen"] == -2000


@pytest.mark.asyncio
async def test_combined_payment_wechat_notify_uses_remainder_amount(
    db: aiosqlite.Connection,
    stored_value_service: StoredValueService,
    order_service: OrderApplicationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """组合支付差额走微信时，通知金额应按差额校验而非订单总额。"""
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-stored")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-stored")
    await _seed_member(db, balance_fen=100_000)
    order_id = await _create_order(order_service, price_fen=5000)
    await stored_value_service.prepare_combined_payment(
        order_id, user_id=USER_ID, balance_fen=2000
    )
    notifier = WechatPaymentNotificationService(order_repo=OrderRepo(db))
    base = {
        "out_trade_no": order_id,
        "mchid": "mch-stored",
        "appid": "appid-stored",
        "trade_state": "SUCCESS",
        "success_time": "2026-08-15T12:00:00+08:00",
        "transaction_id": "4200000000202608121234567890",
    }
    # B3.5（评审问题 4）：币种取 amount.currency（顶层无 currency），字段按真实 v3 报文
    await notifier.validate_transaction(
        {**base, "amount": {"total": 3000, "currency": "CNY"}}
    )
    with pytest.raises(ValueError, match="金额不匹配"):
        await notifier.validate_transaction(
            {**base, "amount": {"total": 5000, "currency": "CNY"}}
        )
    with pytest.raises(ValueError, match="币种"):
        await notifier.validate_transaction(
            {**base, "amount": {"total": 3000, "currency": "USD"}}
        )
