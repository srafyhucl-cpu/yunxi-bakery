"""MiniApp 核心闭环 r56：超时关闭与组合支付微信通知并发候选复核。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.config import settings
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
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.coupon import CouponService
from app.service.coupon.inventory import CouponInventoryService
from app.service.integrations.wechat_pay import WechatPayPrepayResult
from app.service.order import notify_intake
from app.service.order.expiration import OrderExpirationService
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_runtime import OrderPaymentRuntimeService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.order.serialization import OrderSerializationService
from app.service.order.timeline import OrderTimelineService
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
    StoredValueService,
)
from tests.helpers.catalog_seed import seed_catalog_product

ORDER_ID = "order_expire_combined_notify_r56_001"
USER_ID = "wx_expire_combined_notify_r56_001"
OPENID = "expire_combined_notify_r56_001"
MOBILE = "13800003056"
ITEM_ID = 81056
ORDER_AMOUNT_FEN = 10_000
COUPON_FEN = 1_000
BALANCE_FEN = 2_000
EXTERNAL_FEN = ORDER_AMOUNT_FEN - COUPON_FEN - BALANCE_FEN
INITIAL_BALANCE_FEN = 20_000
COUPON_ID = "coupon_expire_combined_notify_r56_001"
TEMPLATE_ID = "template_expire_combined_notify_r56_001"
TRANSACTION_ID = "4200000000202609251234567896"
EVENT_ID = "EV-expire-combined-notify-race-r56-001"


class _FakeWechatPayIntegration:
    """提供本地微信预下单和通知字段，不访问外部网络。"""

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
            appid="appid-expire-combined-notify-r56",
        )

    def build_payment_params(
        self,
        prepay_id: str,
        *,
        signer,
    ) -> dict:
        return {
            "timeStamp": "1789756800",
            "nonceStr": "nonce-r56",
            "package": f"prepay_id={prepay_id}",
            "signType": "RSA",
            "paySign": "signed-r56",
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


def _member_service(handle: DatabaseHandle) -> MemberBalanceService:
    """构建真实会员余额服务。"""
    return MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )


def _coupon_service(handle: DatabaseHandle) -> CouponService:
    """构建真实优惠券服务。"""
    return CouponService(
        template_repo=CouponTemplateRepo(handle),
        inventory_repo=CouponInventoryRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
        order_repo=OrderRepo(handle),
        inventory_service=CouponInventoryService(handle),
    )


def _stored_value_service(
    handle: DatabaseHandle,
    wechat_pay_service: _FakeWechatPayIntegration,
) -> StoredValueService:
    """构建真实余额补偿服务。"""
    member_service = _member_service(handle)
    return StoredValueService(
        member_service=member_service,
        payment_service=StoredValueOrderPaymentService(
            order_repo=OrderRepo(handle),
            member_service=member_service,
            wechat_pay_service=wechat_pay_service,
        ),
    )


def _expiration_service(
    handle: DatabaseHandle,
    wechat_pay_service: _FakeWechatPayIntegration,
) -> OrderExpirationService:
    """构建真实超时关闭服务。"""
    return OrderExpirationService(
        order_repo=OrderRepo(handle),
        inventory_service=OrderInventoryService(
            product_repo=YouzanProductRepo(handle),
            inventory_repo=YouzanInventoryRepo(handle),
        ),
        timeline_service=OrderTimelineService(
            serialization_service=OrderSerializationService(),
            event_repo=OrderEventRepo(handle),
        ),
        stored_value_service=_stored_value_service(handle, wechat_pay_service),
    )


def _payment_service(
    handle: DatabaseHandle,
    wechat_pay_service: _FakeWechatPayIntegration,
) -> OrderPaymentRuntimeService:
    """构建真实微信支付通知运行时。"""
    return OrderPaymentRuntimeService(
        order_repo=OrderRepo(handle),
        wechat_pay_service=wechat_pay_service,
        event_repo=OrderEventRepo(handle),
    )


async def _seed_combined_wechat_order(
    connection: aiosqlite.Connection,
    integration: _FakeWechatPayIntegration,
) -> None:
    """写入已扣余额、已锁微信尾款、已应用券且占用库存的订单。"""
    await seed_catalog_product(
        connection,
        item_id=ITEM_ID,
        title="超时与组合支付并发蛋糕",
        price_fen=ORDER_AMOUNT_FEN,
        stock=1,
    )
    assert await YouzanInventoryRepo(connection).reserve_stock(str(ITEM_ID), 1)
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '超时组合支付并发会员', "
        "'high', 1)",
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
                        "product_id": str(ITEM_ID),
                        "title": "超时与组合支付并发蛋糕",
                        "price_fen": ORDER_AMOUNT_FEN,
                        "quantity": 1,
                        "uses_catalog_inventory": True,
                        "inventory_reserved": True,
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
    await connection.execute(
        "INSERT INTO order_events (order_id, status, operator, note, created_at) "
        "VALUES (?, 'pending', ?, '用户提交订单', ?)",
        (ORDER_ID, f"miniapp:{USER_ID}", now_text()),
    )
    await CouponTemplateRepo(connection).upsert_from_youzan(
        CouponTemplate(
            id=TEMPLATE_ID,
            name="超时组合支付并发测试券",
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
            title="超时组合支付并发测试券",
            value_fen=COUPON_FEN,
            source=LedgerSource.IMPORT,
            occurred_at="2026-08-01 09:00:00",
            template_id=TEMPLATE_ID,
            valid_from="2026-08-01",
            valid_until="2026-12-31",
        )
    )
    await connection.commit()

    handle = DatabaseHandle(connection)
    await _coupon_service(handle).apply_coupon(
        ORDER_ID,
        user_id=USER_ID,
        coupon_id=COUPON_ID,
    )
    payment_service = StoredValueOrderPaymentService(
        order_repo=OrderRepo(handle),
        member_service=_member_service(handle),
        wechat_pay_service=integration,
    )
    result = await payment_service.prepare_combined_payment(
        ORDER_ID,
        user_id=USER_ID,
        balance_fen=BALANCE_FEN,
    )
    assert result["payment"]["status"] == "partial"
    assert result["remainderPayment"]["mode"] == "wechat"
    await connection.commit()


async def _attempt_expire(
    service: OrderExpirationService,
) -> tuple[str, str]:
    """在生产等价事务中执行后台超时关闭。"""
    try:
        async with service._order_repo.transaction():
            result = await service.expire_unpaid_order(ORDER_ID)
            status = str(result["status"])
        return "ok", status
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_payment_notify(
    service: OrderPaymentRuntimeService,
    raw_body: bytes,
) -> tuple[str, dict | str]:
    """执行真实支付通知入口并区分业务冲突与 SQLite 瞬时锁。"""
    try:
        result = await service.handle_wechat_payment_notify(
            raw_body=raw_body,
            headers={},
        )
        return "ok", result
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _read_state(connection: aiosqlite.Connection) -> dict[str, list[dict]]:
    """读取订单、库存、资产和通知事件的最终事实。"""
    queries = {
        "order": (
            "SELECT status, payment FROM orders WHERE id = ?",
            (ORDER_ID,),
        ),
        "product": (
            "SELECT stock FROM youzan_products WHERE item_id = ?",
            (str(ITEM_ID),),
        ),
        "member": (
            "SELECT stored_value_fen, points FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        ),
        "balance_ledger": (
            "SELECT unique_id, amount_fen, balance_after_fen FROM balance_ledger "
            "WHERE biz_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "coupon": (
            "SELECT coupon_id, status, order_no, deducted_fen "
            "FROM coupon_inventory WHERE coupon_id = ? ORDER BY id",
            (COUPON_ID,),
        ),
        "events": (
            "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
            (ORDER_ID,),
        ),
        "transactions": (
            "SELECT transaction_id, order_id FROM payment_transactions "
            "WHERE transaction_id = ?",
            (TRANSACTION_ID,),
        ),
    }
    return {
        name: await connection.execute_fetchall(sql, parameters)
        for name, (sql, parameters) in queries.items()
    }


def _assert_state(
    state: dict[str, list[dict]],
    *,
    first_winner: str,
) -> None:
    """断言超时与通知无论谁先提交都只产生一次资产事实。"""
    assert len(state["order"]) == 1
    order = state["order"][0]
    payment = json.loads(str(order["payment"]))
    if first_winner == "expire":
        assert str(order["status"]) == OrderStatus.CANCELLED.value
        assert str(payment["status"]) == "paid"
        assert str(payment["refundStatus"]) == "pending"
        assert int(payment["refundAmountFen"]) == EXTERNAL_FEN
        assert int(payment["balanceFen"]) == BALANCE_FEN
        assert int(payment["externalPaidFen"]) == EXTERNAL_FEN
        assert [dict(row) for row in state["product"]] == [{"stock": 1}]
        assert [dict(row) for row in state["member"]] == [
            {"stored_value_fen": INITIAL_BALANCE_FEN, "points": 0}
        ]
        assert [dict(row) for row in state["balance_ledger"]] == [
            {
                "unique_id": f"combined_pay:{ORDER_ID}",
                "amount_fen": -BALANCE_FEN,
                "balance_after_fen": INITIAL_BALANCE_FEN - BALANCE_FEN,
            },
            {
                "unique_id": f"order_refund:{ORDER_ID}",
                "amount_fen": BALANCE_FEN,
                "balance_after_fen": INITIAL_BALANCE_FEN,
            },
        ]
        assert [dict(row) for row in state["coupon"]] == [
            {
                "coupon_id": COUPON_ID,
                "status": CouponStatus.TAKE,
                "order_no": "",
                "deducted_fen": 0,
            }
        ]
        assert [dict(row) for row in state["events"]] == [
            {
                "status": "pending",
                "operator": f"miniapp:{USER_ID}",
            },
            {
                "status": OrderStatus.CANCELLED.value,
                "operator": "admin",
            },
            {
                "status": "paid",
                "operator": "wechat-pay",
            },
        ]
    else:
        assert str(order["status"]) == OrderStatus.PENDING.value
        assert str(payment["status"]) == "paid"
        assert "refundStatus" not in payment
        assert int(payment["balanceFen"]) == BALANCE_FEN
        assert int(payment["externalPaidFen"]) == EXTERNAL_FEN
        assert [dict(row) for row in state["product"]] == [{"stock": 0}]
        assert [dict(row) for row in state["member"]] == [
            {
                "stored_value_fen": INITIAL_BALANCE_FEN - BALANCE_FEN,
                "points": EXTERNAL_FEN // 100,
            }
        ]
        assert [dict(row) for row in state["balance_ledger"]] == [
            {
                "unique_id": f"combined_pay:{ORDER_ID}",
                "amount_fen": -BALANCE_FEN,
                "balance_after_fen": INITIAL_BALANCE_FEN - BALANCE_FEN,
            }
        ]
        assert [dict(row) for row in state["coupon"]] == [
            {
                "coupon_id": COUPON_ID,
                "status": CouponStatus.TAKE,
                "order_no": "",
                "deducted_fen": 0,
            },
            {
                "coupon_id": COUPON_ID,
                "status": CouponStatus.CONSUME,
                "order_no": ORDER_ID,
                "deducted_fen": COUPON_FEN,
            },
        ]
        assert [dict(row) for row in state["events"]] == [
            {
                "status": "pending",
                "operator": f"miniapp:{USER_ID}",
            },
            {
                "status": "paid",
                "operator": "wechat-pay",
            },
        ]
    assert [dict(row) for row in state["transactions"]] == [
        {"transaction_id": TRANSACTION_ID, "order_id": ORDER_ID}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("first_winner", ["expire", "payment"])
async def test_timeout_close_and_combined_payment_notify_race_preserves_assets(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    first_winner: str,
) -> None:
    """超时关闭与组合支付通知竞争时只能形成一个正确的资产终态。"""
    database_path = tmp_path / f"expire-combined-notify-{first_winner}-r56.db"
    expiration_connection = await init_db(str(database_path))
    payment_connection = await init_db(str(database_path))
    expiration_handle = DatabaseHandle(expiration_connection)
    payment_handle = DatabaseHandle(payment_connection)
    transaction = {
        "out_trade_no": ORDER_ID,
        "trade_state": "SUCCESS",
        "mchid": "mch-expire-combined-notify-r56",
        "appid": "appid-expire-combined-notify-r56",
        "amount": {"total": EXTERNAL_FEN, "currency": "CNY"},
        "transaction_id": TRANSACTION_ID,
        "success_time": "2026-09-25T12:00:00+08:00",
    }
    integration = _FakeWechatPayIntegration(transaction)
    raw_body = json.dumps(
        {
            "id": EVENT_ID,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    try:
        monkeypatch.setattr(
            settings,
            "WECHAT_PAY_MCH_ID",
            "mch-expire-combined-notify-r56",
        )
        monkeypatch.setattr(
            settings,
            "WECHAT_MINIAPP_APP_ID",
            "appid-expire-combined-notify-r56",
        )
        await _seed_combined_wechat_order(expiration_connection, integration)
        expiration_service = _expiration_service(expiration_handle, integration)
        payment_service = _payment_service(payment_handle, integration)

        initial_read_barrier = asyncio.Barrier(2)
        payment_claim_committed = asyncio.Event()
        winner_committed = asyncio.Event()
        observed_handles: set[int] = set()
        expiration_handle_key = id(expiration_handle)
        payment_handle_key = id(payment_handle)
        original_claim_notify = notify_intake.claim_notify
        original_get_order = OrderRepo.get_order

        async def commit_payment_claim_before_business(
            db,
            event_id: str,
            payload: dict | None = None,
            *,
            lease_seconds: int = notify_intake.DEFAULT_NOTIFY_LEASE_SECONDS,
        ) -> dict:
            """独立提交支付通知认领，避免超时事务制造伪锁。"""
            claim = await original_claim_notify(
                db,
                event_id,
                payload,
                lease_seconds=lease_seconds,
            )
            if id(db) == payment_handle_key:
                await db.commit()
                payment_claim_committed.set()
            return claim

        async def read_old_snapshot_together(
            repo: OrderRepo,
            order_id: str,
        ):
            """让两个入口先读到同一 partial 快照，再固定首胜顺序。"""
            handle_key = id(repo._db)
            if order_id == ORDER_ID and handle_key == expiration_handle_key:
                await asyncio.wait_for(payment_claim_committed.wait(), timeout=5)
            order = await original_get_order(repo, order_id)
            if (
                order_id == ORDER_ID
                and handle_key in {expiration_handle_key, payment_handle_key}
                and handle_key not in observed_handles
            ):
                observed_handles.add(handle_key)
                await asyncio.wait_for(initial_read_barrier.wait(), timeout=5)
                role = "expire" if handle_key == expiration_handle_key else "payment"
                if role != first_winner:
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(
            notify_intake,
            "claim_notify",
            commit_payment_claim_before_business,
        )
        monkeypatch.setattr(OrderRepo, "get_order", read_old_snapshot_together)

        async def run_expiration() -> tuple[str, str]:
            result = await _attempt_expire(expiration_service)
            if first_winner == "expire":
                winner_committed.set()
            return result

        async def run_payment() -> tuple[str, dict | str]:
            result = await _attempt_payment_notify(payment_service, raw_body)
            if first_winner == "payment":
                winner_committed.set()
            return result

        expiration_result, payment_result = await asyncio.gather(
            run_expiration(),
            run_payment(),
        )
        assert observed_handles == {expiration_handle_key, payment_handle_key}
        if first_winner == "expire":
            assert expiration_result == ("ok", OrderStatus.CANCELLED.value)
            assert payment_result[0] == "locked"
            await payment_connection.execute(
                "UPDATE inbox_events SET next_attempt_at = datetime('now', '-1 second') "
                "WHERE message_key = ?",
                (f"wechat_pay_notify:{EVENT_ID}",),
            )
            await payment_connection.commit()
            payment_result = await _attempt_payment_notify(payment_service, raw_body)
            assert payment_result[0] == "ok"
        else:
            assert payment_result[0] == "ok"
            assert expiration_result[0] == "locked"
            expiration_result = await _attempt_expire(expiration_service)
            assert expiration_result[0] in {"ok", "conflict"}
            if expiration_result[0] == "ok":
                assert expiration_result[1] == OrderStatus.PENDING.value

        duplicate_result = await _attempt_payment_notify(payment_service, raw_body)
        await payment_handle.commit()
        assert duplicate_result == ("ok", {"duplicate": True})
        inbox_rows = await payment_connection.execute_fetchall(
            "SELECT status, attempt_count FROM inbox_events WHERE message_key = ?",
            (f"wechat_pay_notify:{EVENT_ID}",),
        )
        assert [dict(row) for row in inbox_rows] == [
            {
                "status": "processed",
                "attempt_count": 2 if first_winner == "expire" else 1,
            }
        ]
        _assert_state(
            await _read_state(expiration_connection),
            first_winner=first_winner,
        )
        assert integration.prepay_amounts == [EXTERNAL_FEN]
    finally:
        await close_db(payment_connection)
        await close_db(expiration_connection)
