"""MiniApp 核心闭环 r35：组合支付预下单期间快照变化候选复核。"""

import asyncio
import json

import aiosqlite
import pytest

from app.database import close_db, init_db
from app.models.coupon import CouponTemplate, CouponType
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.models.order import Order, OrderStatus
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.base import DatabaseHandle
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.coupon import CouponService
from app.service.coupon.inventory import CouponInventoryService
from app.service.integrations.wechat_pay import WechatPayPrepayResult
from app.service.order.cancellation import OrderCancellationService
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.order.serialization import OrderSerializationService
from app.service.order.timeline import OrderTimelineService
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
    StoredValueService,
)
from tests.helpers.legacy_order_catalog import (
    LegacyOrderInventoryRepo,
    LegacyOrderProductRepo,
)

ORDER_ID = "order_combined_prepay_snapshot_r35_001"
USER_ID = "wx_combined_prepay_snapshot_r35_001"
OPENID = "combined_prepay_snapshot_r35_001"
MOBILE = "13800003035"
ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 500
COUPON_ID = "coupon_combined_prepay_snapshot_r35_001"
INITIAL_BALANCE_FEN = 20_000
BALANCE_PAY_FEN = 2_000
FIRST_REMAINDER_FEN = ORDER_AMOUNT_FEN - BALANCE_PAY_FEN
RETRY_REMAINDER_FEN = ORDER_AMOUNT_FEN - COUPON_FEN - BALANCE_PAY_FEN


class _BlockingWechatPayIntegration:
    """让首次预下单等待本地快照提交，并拒绝同订单号换金额。"""

    def __init__(self) -> None:
        self.prepay_started = asyncio.Event()
        self.snapshot_committed = asyncio.Event()
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
        """首次调用形成外部旧会话，金额变化的重试按协议拒绝。"""
        self.prepay_amounts.append(total_fen)
        if len(self.prepay_amounts) == 1:
            self.prepay_started.set()
            await asyncio.wait_for(self.snapshot_committed.wait(), timeout=5)
        elif total_fen != self.prepay_amounts[0]:
            raise ValueError("微信商户订单号已存在且金额不一致")
        return WechatPayPrepayResult(
            prepay_id=f"prepay-{order_id}-{total_fen}",
            appid="appid-r35",
        )

    def build_payment_params(
        self,
        prepay_id: str,
        *,
        signer,
    ) -> dict:
        return {
            "timeStamp": "1789756800",
            "nonceStr": "nonce-r35",
            "package": f"prepay_id={prepay_id}",
            "signType": "RSA",
            "paySign": "signed-r35",
        }

    def sign_with_rsa(self, message: str) -> str:
        return f"signature:{message}"


def _build_member_service(handle: DatabaseHandle) -> MemberBalanceService:
    """为单个数据库连接构建真实会员余额服务。"""
    return MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )


def _build_payment_service(
    handle: DatabaseHandle,
    integration: _BlockingWechatPayIntegration,
) -> StoredValueOrderPaymentService:
    """为单个数据库连接构建真实组合支付服务。"""
    return StoredValueOrderPaymentService(
        order_repo=OrderRepo(handle),
        member_service=_build_member_service(handle),
        wechat_pay_service=integration,
    )


def _build_coupon_service(handle: DatabaseHandle) -> CouponService:
    """为并发券请求构建真实优惠券服务。"""
    return CouponService(
        template_repo=CouponTemplateRepo(handle),
        inventory_repo=CouponInventoryRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
        order_repo=OrderRepo(handle),
        inventory_service=CouponInventoryService(handle),
    )


def _build_cancellation_service(handle: DatabaseHandle) -> OrderCancellationService:
    """为并发取消请求构建生产用户取消服务。"""
    member_service = _build_member_service(handle)
    return OrderCancellationService(
        order_repo=OrderRepo(handle),
        inventory_service=OrderInventoryService(
            product_repo=LegacyOrderProductRepo(handle),
            inventory_repo=LegacyOrderInventoryRepo(handle),
        ),
        timeline_service=OrderTimelineService(
            serialization_service=OrderSerializationService(),
            event_repo=OrderEventRepo(handle),
        ),
        stored_value_service=StoredValueService(
            member_service=member_service,
            payment_service=_build_payment_service(
                handle, _BlockingWechatPayIntegration()
            ),
        ),
    )


async def _seed_order_member_and_coupon(connection: aiosqlite.Connection) -> None:
    """写入待支付订单、会员、足额余额和一张可用券。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '组合预下单快照会员', 'high', 1)",
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
        "VALUES (?, ?, 0)",
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
            products=json.dumps(
                [
                    {
                        "product_id": "p_combined_prepay_snapshot",
                        "title": "组合预下单快照蛋糕",
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
    template_id = "cg_combined_prepay_snapshot_r35_001"
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=template_id,
            name="组合预下单快照测试券",
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
            coupon_group_id=template_id,
            title="组合预下单快照测试券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id=template_id,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()


async def _attempt_combined_payment(
    service: StoredValueOrderPaymentService,
) -> tuple[str, str]:
    """执行一次组合支付并把业务拒绝转换为可断言结果。"""
    try:
        result = await service.prepare_combined_payment(
            ORDER_ID,
            user_id=USER_ID,
            balance_fen=BALANCE_PAY_FEN,
        )
        return "ok", str(result["remainderPayment"]["mode"])
    except ValueError as exc:
        return "conflict", str(exc)


async def _commit_concurrent_snapshot_change(
    handle: DatabaseHandle,
    integration: _BlockingWechatPayIntegration,
    change_kind: str,
) -> str:
    """在首次微信预下单期间提交券快照或用户取消。"""
    await asyncio.wait_for(integration.prepay_started.wait(), timeout=5)
    if change_kind == "coupon":
        service = _build_coupon_service(handle)
        result = await service.apply_coupon(
            ORDER_ID,
            user_id=USER_ID,
            coupon_id=COUPON_ID,
        )
        status = str(result["status"])
    else:
        service = _build_cancellation_service(handle)
        result = await service.cancel_user_order(ORDER_ID, user_id=USER_ID)
        status = str(result["status"])
    await handle.commit()
    integration.snapshot_committed.set()
    return status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change_kind", "expected_initial_conflict"),
    [
        ("coupon", "订单支付快照发生变化，请重新发起支付"),
        ("cancel", "订单已取消"),
    ],
)
async def test_combined_prepay_snapshot_change_never_returns_stale_session(
    tmp_path,
    change_kind: str,
    expected_initial_conflict: str,
) -> None:
    """快照变化后旧组合支付会话不得返回，且本地不得扣余额。"""
    database_path = tmp_path / f"combined-prepay-snapshot-{change_kind}-r35.db"
    payment_connection = await init_db(str(database_path))
    change_connection = await init_db(str(database_path))
    payment_handle = DatabaseHandle(payment_connection)
    change_handle = DatabaseHandle(change_connection)
    try:
        await _seed_order_member_and_coupon(payment_connection)
        integration = _BlockingWechatPayIntegration()
        payment_service = _build_payment_service(payment_handle, integration)

        payment_result, change_status = await asyncio.gather(
            _attempt_combined_payment(payment_service),
            _commit_concurrent_snapshot_change(
                change_handle,
                integration,
                change_kind,
            ),
        )

        order = await OrderRepo(payment_connection).get_order(ORDER_ID)
        balance_rows = await payment_connection.execute_fetchall(
            "SELECT stored_value_fen FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        )
        ledger_rows = await payment_connection.execute_fetchall(
            "SELECT unique_id FROM balance_ledger WHERE biz_id = ?",
            (ORDER_ID,),
        )

        assert payment_result == ("conflict", expected_initial_conflict)
        assert order is not None
        payment = json.loads(order.payment)
        assert int(balance_rows[0]["stored_value_fen"]) == INITIAL_BALANCE_FEN
        assert ledger_rows == []
        assert int(payment.get("balanceFen", 0)) == 0
        assert int(payment.get("externalPaidFen", 0)) == 0
        assert int(payment.get("wechatPrepayFen", 0)) == 0

        if change_kind == "coupon":
            assert change_status == OrderStatus.PENDING.value
            assert str(order.status) == OrderStatus.PENDING.value
            assert str(payment["status"]) == "partial"
            assert str(payment["method"]) == "combined"
            assert str(payment["couponId"]) == COUPON_ID
            assert int(payment["couponFen"]) == COUPON_FEN
            assert int(payment["remainFen"]) == ORDER_AMOUNT_FEN - COUPON_FEN
            coupon_rows = await payment_connection.execute_fetchall(
                "SELECT status, order_no FROM coupon_inventory WHERE coupon_id = ?",
                (COUPON_ID,),
            )
            assert len(coupon_rows) == 1
            assert str(coupon_rows[0]["status"]) == CouponStatus.TAKE
            assert str(coupon_rows[0]["order_no"] or "") == ""

            with pytest.raises(ValueError, match="商户订单号已存在且金额不一致"):
                await payment_service.prepare_combined_payment(
                    ORDER_ID,
                    user_id=USER_ID,
                    balance_fen=BALANCE_PAY_FEN,
                )
            assert integration.prepay_amounts == [
                FIRST_REMAINDER_FEN,
                RETRY_REMAINDER_FEN,
            ]
        else:
            assert change_status == OrderStatus.CANCELLED.value
            assert str(order.status) == OrderStatus.CANCELLED.value
            assert str(payment["status"]) == "unpaid"
            assert integration.prepay_amounts == [FIRST_REMAINDER_FEN]
            with pytest.raises(ValueError, match="订单已取消"):
                await payment_service.prepare_combined_payment(
                    ORDER_ID,
                    user_id=USER_ID,
                    balance_fen=BALANCE_PAY_FEN,
                )
            assert integration.prepay_amounts == [FIRST_REMAINDER_FEN]

        final_order = await OrderRepo(payment_connection).get_order(ORDER_ID)
        final_balance = await payment_connection.execute_fetchall(
            "SELECT stored_value_fen FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        )
        final_ledger = await payment_connection.execute_fetchall(
            "SELECT unique_id FROM balance_ledger WHERE biz_id = ?",
            (ORDER_ID,),
        )
        assert final_order is not None
        assert int(final_balance[0]["stored_value_fen"]) == INITIAL_BALANCE_FEN
        assert final_ledger == []
    finally:
        await close_db(change_connection)
        await close_db(payment_connection)
