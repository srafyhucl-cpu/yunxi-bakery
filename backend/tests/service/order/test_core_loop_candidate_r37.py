"""MiniApp 核心闭环 r37：后台取消与组合支付并发资产一致性。"""

import asyncio
import json
import sqlite3

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.base import DatabaseHandle
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.integrations.wechat_pay import WechatPayPrepayResult
from app.service.order.inventory import OrderInventoryService
from app.service.order.payment_state import build_initial_payment, now_text
from app.service.order.serialization import OrderSerializationService
from app.service.order.status_flow import OrderAdminStatusService
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

MOBILE = "13800003037"
OPENID = "admin_cancel_combined_r37_001"
USER_ID = f"wx_{OPENID}"
ORDER_ID = "order_admin_cancel_combined_r37_001"
INITIAL_BALANCE_FEN = 20_000
ORDER_AMOUNT_FEN = 8_000
BALANCE_PAY_FEN = 2_000
REMAIN_FEN = ORDER_AMOUNT_FEN - BALANCE_PAY_FEN


class _BlockingWechatPayIntegration:
    """让首次微信预下单等待后台取消提交后再返回。"""

    def __init__(self) -> None:
        self.prepay_started = asyncio.Event()
        self.admin_cancel_committed = asyncio.Event()
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
        """形成外部会话前停在事务外，等待取消事实落库。"""
        self.prepay_amounts.append(total_fen)
        self.prepay_started.set()
        await asyncio.wait_for(self.admin_cancel_committed.wait(), timeout=5)
        return WechatPayPrepayResult(
            prepay_id=f"prepay-{order_id}-{total_fen}",
            appid="appid-r37",
        )

    def build_payment_params(
        self,
        prepay_id: str,
        *,
        signer,
    ) -> dict:
        """返回可断言的合成微信支付参数。"""
        return {
            "timeStamp": "1789756800",
            "nonceStr": "nonce-r37",
            "package": f"prepay_id={prepay_id}",
            "signType": "RSA",
            "paySign": "signed-r37",
        }

    def sign_with_rsa(self, message: str) -> str:
        """返回确定性的本地签名占位。"""
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
    integration: _BlockingWechatPayIntegration | None = None,
) -> StoredValueOrderPaymentService:
    """为单个数据库连接构建真实组合支付服务。"""
    return StoredValueOrderPaymentService(
        order_repo=OrderRepo(handle),
        member_service=_build_member_service(handle),
        wechat_pay_service=integration,
    )


def _build_admin_service(handle: DatabaseHandle) -> OrderAdminStatusService:
    """为单个数据库连接构建真实后台订单状态服务。"""
    member_service = _build_member_service(handle)
    return OrderAdminStatusService(
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
            payment_service=_build_payment_service(handle),
        ),
    )


async def _seed_order_and_member(connection: aiosqlite.Connection) -> None:
    """写入待支付订单、会员身份和足额余额。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '后台组合取消竞态会员', 'high', 1)",
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
        "INSERT INTO member_balance (mobile, stored_value_fen) VALUES (?, ?)",
        (MOBILE, INITIAL_BALANCE_FEN),
    )
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id) VALUES (?, 'miniapp', ?)",
        (f"session_{ORDER_ID}", USER_ID),
    )
    await connection.execute(
        "INSERT INTO orders (id, session_id, channel, user_id, products, "
        "total_amount, delivery, payment, status, created_at, updated_at) "
        "VALUES (?, ?, 'miniapp', ?, ?, ?, '{}', ?, 'pending', ?, ?)",
        (
            ORDER_ID,
            f"session_{ORDER_ID}",
            USER_ID,
            json.dumps(
                [
                    {
                        "product_id": "p_admin_cancel_combined_r37",
                        "title": "后台组合取消竞态蛋糕",
                        "price_fen": ORDER_AMOUNT_FEN,
                        "quantity": 1,
                        "inventory_reserved": False,
                    }
                ],
                ensure_ascii=False,
            ),
            ORDER_AMOUNT_FEN / 100,
            json.dumps(build_initial_payment(now_text()), ensure_ascii=False),
            now_text(),
            now_text(),
        ),
    )
    await connection.commit()


async def _attempt_admin_cancel(
    service: OrderAdminStatusService,
) -> tuple[str, str]:
    """在生产应用服务等价事务中执行真实后台取消。"""
    try:
        async with service._order_repo.transaction():
            result = await service.update_admin_order_status(ORDER_ID, "cancelled")
            status = str(result["status"])
        return "ok", status
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _attempt_combined_payment(
    service: StoredValueOrderPaymentService,
) -> tuple[str, str]:
    """执行真实组合支付入口并转换可断言结果。"""
    try:
        result = await service.prepare_combined_payment(
            ORDER_ID,
            user_id=USER_ID,
            balance_fen=BALANCE_PAY_FEN,
        )
        return "ok", str(result["payment"]["status"])
    except ValueError as exc:
        return "conflict", str(exc)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return "locked", str(exc)


async def _read_final_state(
    connection: aiosqlite.Connection,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    """读取订单、余额、余额流水和后台取消事件。"""
    order_rows = await connection.execute_fetchall(
        "SELECT status, payment FROM orders WHERE id = ?",
        (ORDER_ID,),
    )
    balance_rows = await connection.execute_fetchall(
        "SELECT stored_value_fen FROM member_balance WHERE mobile = ?",
        (MOBILE,),
    )
    ledger_rows = await connection.execute_fetchall(
        "SELECT unique_id, amount_fen, balance_after_fen "
        "FROM balance_ledger WHERE biz_id = ? ORDER BY id",
        (ORDER_ID,),
    )
    event_rows = await connection.execute_fetchall(
        "SELECT status, operator FROM order_events WHERE order_id = ? ORDER BY id",
        (ORDER_ID,),
    )
    return order_rows, balance_rows, ledger_rows, event_rows


def _assert_admin_cancel_event(
    event_rows: list[dict[str, object]],
) -> None:
    """最终只能保留一个后台取消事件。"""
    assert len(event_rows) == 1
    assert str(event_rows[0]["status"]) == "cancelled"
    assert str(event_rows[0]["operator"]) == "admin"


@pytest.mark.asyncio
@pytest.mark.parametrize("winner", ["admin", "payment"])
async def test_admin_cancel_and_combined_payment_commit_race_preserves_assets(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    winner: str,
) -> None:
    """余额腿提交与后台取消并发后只能无扣款取消或扣退各一次。"""
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
    database_path = tmp_path / f"admin-cancel-combined-commit-{winner}-r37.db"
    admin_connection = await init_db(str(database_path))
    payment_connection = await init_db(str(database_path))
    admin_handle = DatabaseHandle(admin_connection)
    payment_handle = DatabaseHandle(payment_connection)
    try:
        await _seed_order_and_member(admin_connection)
        admin_service = _build_admin_service(admin_handle)
        payment_service = _build_payment_service(payment_handle)

        initial_read_barrier = asyncio.Barrier(2)
        admin_committed = asyncio.Event()
        payment_committed = asyncio.Event()
        winner_committed = admin_committed if winner == "admin" else payment_committed
        admin_handle_key = id(admin_handle)
        first_read_handles: set[int] = set()
        original_get_order = OrderRepo.get_order

        async def synchronized_initial_order_read(
            repo: OrderRepo,
            order_id: str,
        ):
            """同步两个请求的首次旧快照读取并固定胜出顺序。"""
            order = await original_get_order(repo, order_id)
            handle_key = id(repo._db)
            if handle_key not in first_read_handles:
                first_read_handles.add(handle_key)
                await asyncio.wait_for(initial_read_barrier.wait(), timeout=5)
                role = "admin" if handle_key == admin_handle_key else "payment"
                if role != winner:
                    await asyncio.wait_for(winner_committed.wait(), timeout=5)
            return order

        monkeypatch.setattr(OrderRepo, "get_order", synchronized_initial_order_read)

        async def run_admin_cancel() -> tuple[str, str]:
            """执行后台取消并在提交后释放等待方。"""
            result = await _attempt_admin_cancel(admin_service)
            admin_committed.set()
            return result

        async def run_payment() -> tuple[str, str]:
            """执行组合支付并在提交后释放等待方。"""
            result = await _attempt_combined_payment(payment_service)
            payment_committed.set()
            return result

        admin_result, payment_result = await asyncio.gather(
            run_admin_cancel(),
            run_payment(),
        )
        admin_retry_result = None
        if winner == "payment" and admin_result[0] == "locked":
            admin_retry_result = await _attempt_admin_cancel(admin_service)

        order_rows, balance_rows, ledger_rows, event_rows = await _read_final_state(
            admin_connection
        )
        assert len(order_rows) == 1
        assert len(balance_rows) == 1
        assert str(order_rows[0]["status"]) == "cancelled"
        payment = json.loads(str(order_rows[0]["payment"]))
        _assert_admin_cancel_event(event_rows)

        if winner == "admin":
            assert admin_result == ("ok", "cancelled")
            assert payment_result[0] in {"conflict", "locked"}
            assert str(payment["status"]) == "unpaid"
            assert int(balance_rows[0]["stored_value_fen"]) == INITIAL_BALANCE_FEN
            assert ledger_rows == []
        else:
            assert payment_result == ("ok", "partial")
            assert admin_result[0] in {"ok", "locked"}
            if admin_result[0] == "locked":
                assert admin_retry_result == ("ok", "cancelled")
            else:
                assert admin_result == ("ok", "cancelled")
                assert admin_retry_result is None
            assert str(payment["status"]) == "partial"
            assert int(payment["balanceFen"]) == BALANCE_PAY_FEN
            assert int(payment["remainFen"]) == REMAIN_FEN
            assert int(payment["externalPaidFen"]) == REMAIN_FEN
            assert int(balance_rows[0]["stored_value_fen"]) == INITIAL_BALANCE_FEN
            assert len(ledger_rows) == 2
            assert str(ledger_rows[0]["unique_id"]) == f"combined_pay:{ORDER_ID}"
            assert int(ledger_rows[0]["amount_fen"]) == -BALANCE_PAY_FEN
            assert int(ledger_rows[0]["balance_after_fen"]) == (
                INITIAL_BALANCE_FEN - BALANCE_PAY_FEN
            )
            assert str(ledger_rows[1]["unique_id"]) == f"order_refund:{ORDER_ID}"
            assert int(ledger_rows[1]["amount_fen"]) == BALANCE_PAY_FEN
            assert int(ledger_rows[1]["balance_after_fen"]) == INITIAL_BALANCE_FEN
    finally:
        await close_db(payment_connection)
        await close_db(admin_connection)


@pytest.mark.asyncio
async def test_admin_cancel_during_combined_prepay_never_returns_stale_session(
    tmp_path,
) -> None:
    """预下单期间取消后不得返回旧会话、扣余额或生成额外事件。"""
    database_path = tmp_path / "admin-cancel-combined-prepay-r37.db"
    admin_connection = await init_db(str(database_path))
    payment_connection = await init_db(str(database_path))
    admin_handle = DatabaseHandle(admin_connection)
    payment_handle = DatabaseHandle(payment_connection)
    try:
        await _seed_order_and_member(admin_connection)
        integration = _BlockingWechatPayIntegration()
        payment_service = _build_payment_service(payment_handle, integration)
        admin_service = _build_admin_service(admin_handle)

        async def cancel_during_prepay() -> tuple[str, str]:
            """等待预下单开始后提交后台取消。"""
            await asyncio.wait_for(integration.prepay_started.wait(), timeout=5)
            result = await _attempt_admin_cancel(admin_service)
            integration.admin_cancel_committed.set()
            return result

        payment_result, admin_result = await asyncio.gather(
            _attempt_combined_payment(payment_service),
            cancel_during_prepay(),
        )
        order_rows, balance_rows, ledger_rows, event_rows = await _read_final_state(
            admin_connection
        )

        assert payment_result == ("conflict", "订单已取消")
        assert admin_result == ("ok", "cancelled")
        assert integration.prepay_amounts == [REMAIN_FEN]
        assert len(order_rows) == 1
        assert str(order_rows[0]["status"]) == "cancelled"
        payment = json.loads(str(order_rows[0]["payment"]))
        assert str(payment["status"]) == "unpaid"
        assert int(payment.get("balanceFen", 0)) == 0
        assert int(payment.get("externalPaidFen", 0)) == 0
        assert int(payment.get("wechatPrepayFen", 0)) == 0
        assert len(balance_rows) == 1
        assert int(balance_rows[0]["stored_value_fen"]) == INITIAL_BALANCE_FEN
        assert ledger_rows == []
        _assert_admin_cancel_event(event_rows)
    finally:
        await close_db(payment_connection)
        await close_db(admin_connection)
