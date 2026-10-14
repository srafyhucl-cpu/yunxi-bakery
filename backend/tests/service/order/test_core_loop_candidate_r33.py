"""MiniApp 核心闭环 r33：微信预支付后积分改价候选复核。"""

import json

import aiosqlite
import pytest

from app.config import settings
from app.models.order import Order, OrderStatus
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_repo import OrderRepo
from app.repository.points_ledger_repo import PointsLedgerRepo
from app.service.integrations.wechat_pay import WechatPayPrepayResult
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.points import PointsService
from app.service.points.payment import POINTS_DEDUCTION_FENCE

ORDER_ID = "order_wechat_points_fence_001"
USER_ID = "wx_wechat_points_fence_001"
OPENID = "wechat_points_fence_001"
MOBILE = "13800003033"
ORDER_AMOUNT_FEN = 10_000
INITIAL_POINTS = 100_000
EXPECTED_REDEEM_POINTS = 5_000
EXPECTED_REDEEM_FEN = 5_000
TRANSACTION_ID = "4200000000202609251234567891"
EVENT_ID = "EV-wechat-points-fence-001"


class _FakeWechatPayIntegration:
    """记录预支付金额并返回确定性的本地微信结果。"""

    def __init__(self, transaction: dict) -> None:
        self.transaction = transaction
        self.prepay_amounts: list[int] = []

    def is_ready(self) -> bool:
        return True

    async def create_jsapi_prepay(
        self,
        *,
        order_id: str,
        total_fen: int,
        description: str,
        payer_openid: str,
    ) -> WechatPayPrepayResult:
        self.prepay_amounts.append(total_fen)
        return WechatPayPrepayResult(
            prepay_id=f"prepay-{order_id}-{total_fen}",
            appid=settings.WECHAT_MINIAPP_APP_ID,
        )

    def build_payment_params(
        self,
        prepay_id: str,
        *,
        signer,
    ) -> dict:
        return {
            "timeStamp": "1789756800",
            "nonceStr": "nonce-r33",
            "package": f"prepay_id={prepay_id}",
            "signType": "RSA",
            "paySign": "signed-r33",
        }

    def verify_notify_signature(
        self,
        raw_body: bytes,
        headers: dict[str, str],
        *,
        now_seconds: int | None = None,
    ) -> bool:
        return True

    def decrypt_notify_resource(self, resource: dict) -> dict:
        return dict(self.transaction)

    def format_success_time(self, value: str) -> str:
        return "2026-09-25 12:00:00"

    def sign_with_rsa(self, message: str) -> str:
        return f"signature:{message}"


async def _seed_order_and_member(connection: aiosqlite.Connection) -> None:
    """写入待支付订单、微信身份和可抵扣积分账户。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '微信预支付积分围栏会员', 'high', 1)",
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
        "INSERT INTO member_balance (mobile, stored_value_fen, points) "
        "VALUES (?, 0, ?)",
        (MOBILE, INITIAL_POINTS),
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
            products=json.dumps(
                [
                    {
                        "product_id": "p_wechat_points_fence",
                        "title": "微信预支付积分围栏蛋糕",
                        "price_fen": ORDER_AMOUNT_FEN,
                        "quantity": 1,
                        "inventory_reserved": False,
                    }
                ],
                ensure_ascii=False,
            ),
            total_amount=ORDER_AMOUNT_FEN / 100,
            delivery=json.dumps({}, ensure_ascii=False),
            payment=json.dumps(build_initial_payment(now_text()), ensure_ascii=False),
            status=OrderStatus.PENDING,
            remark="",
            created_at=now_text(),
            updated_at=now_text(),
        )
    )
    await connection.commit()


async def _points_state(connection: aiosqlite.Connection) -> tuple[int, list[dict]]:
    """读取当前积分余额和该订单关联的积分流水。"""
    balance_rows = await connection.execute_fetchall(
        "SELECT points FROM member_balance WHERE mobile = ?",
        (MOBILE,),
    )
    ledger_rows = await connection.execute_fetchall(
        "SELECT unique_id, amount, event_type, biz_id FROM points_ledger "
        "WHERE mobile = ? AND biz_id = ? ORDER BY id",
        (MOBILE, ORDER_ID),
    )
    return int(balance_rows[0]["points"]), [dict(row) for row in ledger_rows]


@pytest.mark.asyncio
async def test_wechat_prepay_blocks_points_application_under_active_fence(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """现行积分围栏下，微信预支付后不得写入新的积分支付快照。"""
    assert POINTS_DEDUCTION_FENCE is True
    await _seed_order_and_member(db)
    transaction = {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": "mch-r33",
        "appid": "appid-r33",
        "amount": {"total": ORDER_AMOUNT_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T12:00:00+08:00",
    }
    integration = _FakeWechatPayIntegration(transaction)
    order_repo = OrderRepo(db)
    runtime = OrderPaymentRuntimeService(order_repo, integration)
    points_service = PointsService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=PointsLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
        order_repo=order_repo,
    )
    monkeypatch.setattr(settings, "WECHAT_PAY_MCH_ID", "mch-r33")
    monkeypatch.setattr(settings, "WECHAT_MINIAPP_APP_ID", "appid-r33")

    session = await runtime.prepare_payment(ORDER_ID, user_id=USER_ID)
    await db.commit()
    preview = await points_service.redeem_preview(ORDER_ID, user_id=USER_ID)
    after_preview = await order_repo.get_order(ORDER_ID)

    assert after_preview is not None
    preview_payment = json.loads(after_preview.payment)
    assert session.mode == "wechat"
    assert preview["pointsUsed"] == EXPECTED_REDEEM_POINTS
    assert preview["pointsFen"] == EXPECTED_REDEEM_FEN
    assert preview["remainFen"] == EXPECTED_REDEEM_FEN
    assert str(preview_payment["status"]) == "unpaid"
    assert int(preview_payment["externalPaidFen"]) == ORDER_AMOUNT_FEN
    assert int(preview_payment["wechatPrepayFen"]) == ORDER_AMOUNT_FEN
    assert "pointsFen" not in preview_payment
    assert "pointsUsed" not in preview_payment

    with pytest.raises(ValueError, match="积分抵扣已临时关闭"):
        await points_service.apply_points(ORDER_ID, user_id=USER_ID)

    after_rejection = await order_repo.get_order(ORDER_ID)
    points_after_rejection, ledger_after_rejection = await _points_state(db)
    assert after_rejection is not None
    rejected_payment = json.loads(after_rejection.payment)
    assert str(rejected_payment["status"]) == "unpaid"
    assert int(rejected_payment["externalPaidFen"]) == ORDER_AMOUNT_FEN
    assert int(rejected_payment["wechatPrepayFen"]) == ORDER_AMOUNT_FEN
    assert "pointsFen" not in rejected_payment
    assert "pointsUsed" not in rejected_payment
    assert points_after_rejection == INITIAL_POINTS
    assert ledger_after_rejection == []

    paid = await runtime.handle_wechat_payment_notify(
        raw_body=json.dumps(
            {
                "id": EVENT_ID,
                "event_type": "TRANSACTION.SUCCESS",
                "resource": {},
            }
        ).encode("utf-8"),
        headers={},
    )
    final_order = await order_repo.get_order(ORDER_ID)
    points_after_payment, ledger_after_payment = await _points_state(db)
    transactions = await db.execute_fetchall(
        "SELECT transaction_id FROM payment_transactions WHERE order_id = ?",
        (ORDER_ID,),
    )

    assert final_order is not None
    final_payment = json.loads(final_order.payment)
    assert str(paid["paymentStatus"]) == "paid"
    assert str(paid["paymentMethod"]) == "wechat"
    assert int(final_payment["externalPaidFen"]) == ORDER_AMOUNT_FEN
    assert int(final_payment["wechatPrepayFen"]) == ORDER_AMOUNT_FEN
    assert "pointsFen" not in final_payment
    assert int(final_payment.get("pointsUsed", 0)) == 0
    assert points_after_payment == INITIAL_POINTS + ORDER_AMOUNT_FEN // 100
    assert len(ledger_after_payment) == 1
    assert ledger_after_payment[0]["unique_id"] == f"points:award:{ORDER_ID}"
    assert ledger_after_payment[0]["event_type"] == "order_award"
    assert int(ledger_after_payment[0]["amount"]) == ORDER_AMOUNT_FEN // 100
    assert [str(row["transaction_id"]) for row in transactions] == [TRANSACTION_ID]
