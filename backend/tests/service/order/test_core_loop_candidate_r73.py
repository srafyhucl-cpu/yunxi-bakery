"""MiniApp 核心闭环 r73：主体删除与储值退款的三个候选复核。

本轮不预设结论，对三个怀疑各写最小复现，用「守卫是否承重」的变异探针
区分真实缺陷与漏判：

候选一（真实 P1）：`PrivacyRepo.delete_subject` 无条件删除
`orders WHERE user_id = ?`，但组合支付已把储值腿记在
`balance_ledger`（`combined_pay:{id}`）并已扣减
`member_balance.stored_value_fen`。`balance_ledger` 对 `orders` 无外键，
于是订单被销毁后，被扣储值既没有可退回的订单对象，也没有任何
对账案件：金额永久滞留，调用方无从察觉。

候选二（排除）：取消后迟到支付只写 `refundStatus=pending` 而不建对账案件，
看似与其他异常路径不对称。但 `miniapp/docs/api-contract.md:798` 明确
规定该路径「不得重新核销优惠券、发放积分、占用库存或自动发起微信退款」，
属于契约显式设计，本文件按契约逐条验证实现与文档一致。

候选三（r76 更正结论）：`refund_order_balance` 退款时重新解析会员账户，
怀疑账户无法解析时取消/超时活锁。r73 当时以「`_customer_ids` 恒不命中、
置空分支不可达」为由排除该候选，但该前提本身是缺陷：身份链存裸 openid、
传入的却是 `wx_` 前缀 user_id，匹配恒失效。r76 修好匹配后，主档层会被
真实销毁，因此真正保护退款的不变量是「结清先于销毁、且同事务」——
`PrivacyLifecycleService.delete_subject` 先 `_settle_holding_stored_value`
再 `_privacy_repo.delete_subject`，结清失败即整体回滚。相应断言已重写为
验证结清先于销毁。

候选四（修复回归护栏）：结清逻辑只处理「仍占用储值」的订单。已支付订单的
储值已换货、不属占用，主体删除时不得把它当成待退款额退回，否则等于凭空
增发储值。本文件用已支付订单验证结清不会误退。
"""

import json

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.models.order import Order, OrderStatus
from app.repository.base import DatabaseHandle
from app.repository.order_repo import OrderRepo
from app.repository.privacy_repo import PrivacyRepo
from app.service.order.payment_state import loads_payment, now_text
from app.service.privacy_lifecycle import PrivacyLifecycleService
from tests.service.order.test_core_loop_candidate_r41 import _build_payment_service

MOBILE = "13800003073"
OPENID = "core_loop_r73_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_core_loop_r73_001"
ORDER_AMOUNT_FEN = 10_000
INITIAL_BALANCE_FEN = 30_000
COMBINED_BALANCE_FEN = 3_000
MCH_ID = "mch-core-loop-r73"
APP_ID = "appid-core-loop-r73"
TRANSACTION_ID = "4200000000202609267300000001"
PAY_EVENT_ID = "EV-core-loop-r73-pay"


async def _seed_member_and_order(connection: aiosqlite.Connection) -> None:
    """写入会员身份链、储值账户行与待支付订单。

    身份链按生产口径存裸 openid（`preimport_youzan_customer_openids.py`
    经 `build_miniapp_openid_identity` 写入），订单 `user_id` 则是
    `wx_` 前缀形式，这一差异正是候选三的关键。
    """
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


async def _read_stored_value(connection: aiosqlite.Connection) -> int:
    """读取本地储值余额。"""
    rows = await connection.execute_fetchall(
        "SELECT stored_value_fen FROM member_balance WHERE mobile = ?", (MOBILE,)
    )
    return int(rows[0]["stored_value_fen"]) if rows else 0


async def _read_reconcile_cases(connection: aiosqlite.Connection) -> list[str]:
    """读取本订单的退款对账案件原因。"""
    rows = await connection.execute_fetchall(
        "SELECT reason FROM points_refund_reconcile WHERE order_id = ? ORDER BY id",
        (ORDER_ID,),
    )
    return [str(row["reason"]) for row in rows]


@pytest.mark.asyncio
async def test_subject_erasure_must_not_orphan_outstanding_stored_value(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """主体删除不得让已扣储值失去退款凭据。

    怀疑：`delete_subject` 直接删订单，而组合支付已把储值腿扣掉并记在
    `balance_ledger`，账本对订单无外键，于是订单消失后被扣金额既无法退回
    也不建案。验证：组合支付后储值确实已扣、订单确实 `partial`；执行主体
    删除后断言「余额已原路退回」或「订单仍可退回」二者至少成立。
    """
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)

    connection = await init_db(str(tmp_path / "privacy-orphan-r73.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        payment_service = _build_payment_service(handle)

        combined = await payment_service.prepare_combined_payment(
            ORDER_ID,
            user_id=USER_ID,
            balance_fen=COMBINED_BALANCE_FEN,
        )
        assert combined["payment"]["status"] == "partial"
        assert int(combined["payment"]["balanceFen"]) == COMBINED_BALANCE_FEN
        # 前置事实：储值已真实扣减，订单处于待付尾款的 partial 态。
        assert await _read_stored_value(connection) == (
            INITIAL_BALANCE_FEN - COMBINED_BALANCE_FEN
        )
        order_before = await OrderRepo(handle).get_order(ORDER_ID)
        assert order_before is not None
        assert int(loads_payment(order_before.payment)["balanceFen"]) == (
            COMBINED_BALANCE_FEN
        )

        await PrivacyLifecycleService(PrivacyRepo(handle)).delete_subject(USER_ID)

        # 关键断言：主体删除后，被扣储值必须仍有可退路径。
        # 要么余额已原路退回，要么订单仍在、可由取消/超时链路退回。
        balance_after = await _read_stored_value(connection)
        order_after = await OrderRepo(handle).get_order(ORDER_ID)
        assert balance_after == INITIAL_BALANCE_FEN or order_after is not None, (
            f"已扣储值 {COMBINED_BALANCE_FEN} 分失去退款凭据："
            f"余额={balance_after}（初始 {INITIAL_BALANCE_FEN}），"
            f"订单存在={order_after is not None}，且未建立任何对账案件"
        )
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_late_payment_after_cancellation_matches_contract(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """取消后迟到支付必须严格符合契约，且不产生任何资产副作用。

    怀疑：该路径只写 `refundStatus=pending` 而不建对账案件，与
    `refund_notification` 处处建案不对称。验证契约
    `miniapp/docs/api-contract.md:798` 的逐条要求：履约保持 `cancelled`、
    原子记录 `paid`/交易号/到账时间、写 `pending` 与金额、同一交易号
    重复通知幂等，且不核销券、不发分、不占库存、不自动退款。
    """
    from app.repository.order_event_repo import OrderEventRepo
    from app.service.order.payment_runtime import OrderPaymentRuntimeService
    from tests.service.order.test_core_loop_candidate_r72 import _MockWechatPay

    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
    monkeypatch.setattr(
        "app.service.order.payment_notification.settings.WECHAT_PAY_MCH_ID", MCH_ID
    )
    monkeypatch.setattr(
        "app.service.order.payment_notification.settings.WECHAT_MINIAPP_APP_ID", APP_ID
    )

    connection = await init_db(str(tmp_path / "late-payment-r73.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        order_repo = OrderRepo(handle)

        await connection.execute(
            "UPDATE orders SET status = 'cancelled', updated_at = ? WHERE id = ?",
            (now_text(), ORDER_ID),
        )
        await connection.commit()

        wechat = _MockWechatPay()
        wechat.current = {
            "out_trade_no": ORDER_ID,
            "trade_state": "SUCCESS",
            "mchid": MCH_ID,
            "appid": APP_ID,
            "amount": {"total": ORDER_AMOUNT_FEN, "currency": "CNY"},
            "transaction_id": TRANSACTION_ID,
            "success_time": "2026-09-26T19:00:00+08:00",
        }
        notify = json.dumps(
            {
                "id": PAY_EVENT_ID,
                "event_type": "TRANSACTION.SUCCESS",
                "resource": {"kind": "transaction"},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {
            "Wechatpay-Signature": "sig",
            "Wechatpay-Timestamp": "1793000000",
            "Wechatpay-Nonce": "nonce",
            "Wechatpay-Serial": "serial",
        }

        runtime = OrderPaymentRuntimeService(
            order_repo=order_repo,
            wechat_pay_service=wechat,
            event_repo=OrderEventRepo(handle),
        )
        await runtime.handle_wechat_payment_notify(raw_body=notify, headers=headers)

        order = await order_repo.get_order(ORDER_ID)
        assert order is not None
        payment = loads_payment(order.payment)
        # 契约：履约终态保持 cancelled，原子记录外部到账事实。
        assert order.status == OrderStatus.CANCELLED.value
        assert payment["status"] == "paid"
        assert payment["transactionId"] == TRANSACTION_ID
        assert str(payment["paidAt"]) != ""
        # 契约：无既有退款事实时写 pending 与金额。
        assert payment["refundStatus"] == "pending"
        assert int(payment["refundAmountFen"]) == ORDER_AMOUNT_FEN
        assert payment["refundReason"] == "late_payment_after_cancellation"
        # 契约：该路径不得有任何资产副作用，因此也不建对账案件。
        assert await _read_reconcile_cases(connection) == []
        ledger = await connection.execute_fetchall(
            "SELECT unique_id FROM balance_ledger WHERE biz_id = ?", (ORDER_ID,)
        )
        assert ledger == []

        # 契约：同一交易号重复通知必须幂等。
        await runtime.handle_wechat_payment_notify(raw_body=notify, headers=headers)
        replay_order = await order_repo.get_order(ORDER_ID)
        assert replay_order is not None
        replay = loads_payment(replay_order.payment)
        assert replay["refundStatus"] == "pending"
        assert int(replay["refundAmountFen"]) == ORDER_AMOUNT_FEN
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_stored_value_settles_before_customer_layer_erasure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """储值结清必须发生在客户主档层被销毁之前。

    r73 曾把「客户主档与身份链在删除后仍完好」当作期望写进断言，理由是
    `_customer_ids` 用裸 `user_id` 匹配、而身份链存裸 openid，所以恒不命中。
    r76 修好该匹配后，那条断言的前提被推翻：主档层现在会被真实删除。

    此处重写为真正保护退款的不变量：`refund_order_balance` 依赖
    `resolve_mobile` 读 `customer_identity_links` 与 `customer_master`，而主体
    删除会销毁这两张表。因此结清必须在删除之前、同一事务内完成，否则
    储值退款会因无法解析账户而失败。
    """
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)

    connection = await init_db(str(tmp_path / "refund-account-r73.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        payment_service = _build_payment_service(handle)
        member_service = payment_service._member_service
        # 前置事实：结清前账户可解析，否则退款路径本就无从谈起。
        assert await member_service.resolve_mobile(USER_ID) == MOBILE

        # 造一笔真实占用储值的 partial 订单：结清路径必须解析账户后退款。
        combined = await payment_service.prepare_combined_payment(
            ORDER_ID, user_id=USER_ID, balance_fen=COMBINED_BALANCE_FEN
        )
        assert combined["payment"]["status"] == "partial"
        assert await _read_stored_value(connection) == (
            INITIAL_BALANCE_FEN - COMBINED_BALANCE_FEN
        )

        await PrivacyLifecycleService(PrivacyRepo(handle)).delete_subject(USER_ID)

        # 关键断言：结清先于销毁完成，储值已全额原路退回。
        assert await _read_stored_value(connection) == INITIAL_BALANCE_FEN
        # 客户主档层按隐私口径销毁：身份链与主档都不再残留。
        links = await connection.execute_fetchall(
            "SELECT id FROM customer_identity_links WHERE customer_id = ?",
            (f"cm_{ORDER_ID}",),
        )
        assert links == []
        masters = await connection.execute_fetchall(
            "SELECT id FROM customer_master WHERE id = ?",
            (f"cm_{ORDER_ID}",),
        )
        assert masters == []
        # 储值账本对 orders 无外键，扣减与结清两条流水都必须留存可对账证据。
        ledger = await connection.execute_fetchall(
            "SELECT unique_id FROM balance_ledger WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        )
        assert [str(row["unique_id"]) for row in ledger] == [
            f"combined_pay:{ORDER_ID}",
            f"order_refund:{ORDER_ID}",
        ]
    finally:
        await close_db(connection)


@pytest.mark.asyncio
async def test_subject_erasure_must_not_refund_settled_stored_value(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """主体删除不得把已支付订单的储值当成待退款额退回。

    这是结清修复自身引入的风险护栏：已支付订单的储值已经换货，
    `paymentStatus=paid` 不在占用集合内，删除主体时余额必须保持已扣状态，
    不得凭空增发储值。
    """
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)

    connection = await init_db(str(tmp_path / "privacy-settled-r73.db"))
    handle = DatabaseHandle(connection)
    try:
        await _seed_member_and_order(connection)
        payment_service = _build_payment_service(handle)

        paid = await payment_service.pay_order_with_balance(ORDER_ID, user_id=USER_ID)
        assert paid["paymentStatus"] == "paid"
        settled_balance = INITIAL_BALANCE_FEN - ORDER_AMOUNT_FEN
        assert await _read_stored_value(connection) == settled_balance

        await PrivacyLifecycleService(PrivacyRepo(handle)).delete_subject(USER_ID)

        # 关键断言：已支付订单的储值不得被当作占用额退回。
        assert await _read_stored_value(connection) == settled_balance
        assert await OrderRepo(handle).get_order(ORDER_ID) is None
    finally:
        await close_db(connection)
