"""MiniApp 核心闭环 r19：充值取消与支付并发只允许一个状态胜者。"""

import asyncio
import sqlite3

import aiosqlite
import pytest

from app.config import settings
from app.database import close_db, init_db
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.recharge_repo import RechargeRepo
from app.repository.base import DatabaseHandle
from app.service.stored_value.member import MemberBalanceService
from app.service.stored_value.recharge import RechargeService

MOBILE = "13800001919"
OPENID = "openid_recharge_race_001"
USER_ID = f"wx_{OPENID}"
RECHARGE_AMOUNT_FEN = 5000


def _build_service(handle: DatabaseHandle) -> RechargeService:
    """为单个数据库连接构建完整充值服务。"""
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(handle),
        ledger_repo=BalanceLedgerRepo(handle),
        customer_repo=CustomerMasterRepo(handle),
    )
    return RechargeService(
        recharge_repo=RechargeRepo(handle),
        member_service=member_service,
    )


async def _seed_member(connection: aiosqlite.Connection) -> None:
    """写入可充值会员和零余额账户。"""
    await connection.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '充值竞态会员', 'high', 1)",
        (f"cm_{OPENID}", MOBILE),
    )
    await connection.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (f"cil_{OPENID}", f"cm_{OPENID}", OPENID, OPENID),
    )
    await connection.execute(
        "INSERT INTO member_balance (mobile, stored_value_fen) VALUES (?, 0)",
        (MOBILE,),
    )
    await connection.commit()


@pytest.mark.asyncio
async def test_recharge_cancel_and_mock_payment_race_has_single_winner(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两端同时读到未支付后，取消和支付只能有一个状态转换胜出。"""
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENT", True)
    database_path = tmp_path / "recharge-cancel-pay-race.db"
    connection_a = await init_db(str(database_path))
    connection_b = await init_db(str(database_path))
    handle_a = DatabaseHandle(connection_a)
    handle_b = DatabaseHandle(connection_b)
    try:
        await _seed_member(connection_a)
        service_a = _build_service(handle_a)
        service_b = _build_service(handle_b)
        created = await service_a.create_recharge(USER_ID, RECHARGE_AMOUNT_FEN)
        recharge_id = created["rechargeId"]

        initial_read_barrier = asyncio.Barrier(2)
        first_read_handles: set[int] = set()
        original_get = RechargeRepo.get

        async def synchronized_initial_read(
            repo: RechargeRepo,
            requested_recharge_id: str,
        ):
            """只同步两个服务的第一笔状态读取。"""
            recharge = await original_get(repo, requested_recharge_id)
            handle_key = id(repo._db)
            if handle_key not in first_read_handles:
                first_read_handles.add(handle_key)
                await initial_read_barrier.wait()
            return recharge

        monkeypatch.setattr(RechargeRepo, "get", synchronized_initial_read)

        async def attempt(
            service: RechargeService,
            action: str,
        ) -> tuple[str, str]:
            """模拟一个由请求中间件提交的独立充值请求。"""
            try:
                async with service._recharge_repo.transaction():
                    try:
                        if action == "cancel":
                            result = await service.cancel_unpaid_recharge(
                                recharge_id,
                                user_id=USER_ID,
                            )
                        else:
                            result = await service.confirm_mock_recharge_payment(
                                recharge_id,
                                user_id=USER_ID,
                            )
                        return "ok", str(result["status"])
                    except ValueError as exc:
                        return "conflict", str(exc)
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                return "locked", str(exc)

        results = await asyncio.gather(
            attempt(service_a, "cancel"),
            attempt(service_b, "pay"),
        )

        assert sum(outcome == "ok" for outcome, _ in results) == 1
        assert any(outcome == "locked" for outcome, _ in results) or all(
            outcome == "conflict" for outcome, _ in results if outcome != "ok"
        )

        recharge_rows = await connection_a.execute_fetchall(
            "SELECT status, payment_method, paid_at FROM stored_value_recharge "
            "WHERE id = ?",
            (recharge_id,),
        )
        balance_rows = await connection_a.execute_fetchall(
            "SELECT stored_value_fen FROM member_balance WHERE mobile = ?",
            (MOBILE,),
        )
        ledger_rows = await connection_a.execute_fetchall(
            "SELECT amount_fen, balance_after_fen, biz_type, biz_id "
            "FROM balance_ledger WHERE unique_id = ?",
            (f"recharge:{recharge_id}",),
        )

        assert len(recharge_rows) == 1
        assert len(balance_rows) == 1
        final_status = str(recharge_rows[0]["status"])
        assert ("ok", final_status) in results
        if final_status == "paid":
            assert int(balance_rows[0]["stored_value_fen"]) == RECHARGE_AMOUNT_FEN
            assert len(ledger_rows) == 1
            assert int(ledger_rows[0]["amount_fen"]) == RECHARGE_AMOUNT_FEN
            assert int(ledger_rows[0]["balance_after_fen"]) == RECHARGE_AMOUNT_FEN
            assert str(recharge_rows[0]["payment_method"]) == "mock"
            assert recharge_rows[0]["paid_at"]
        else:
            assert final_status == "cancelled"
            assert int(balance_rows[0]["stored_value_fen"]) == 0
            assert ledger_rows == []
            assert not recharge_rows[0]["paid_at"]
    finally:
        await close_db(connection_b)
        await close_db(connection_a)
