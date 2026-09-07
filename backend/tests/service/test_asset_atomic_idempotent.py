"""储值与积分账务原子幂等测试。"""

import asyncio

import pytest

from app.config import settings
from app.database import close_db, db_session_scope, init_db
from app.repository.member_balance_repo import MemberBalanceRepo
from app.service.points.ledger import PointsLedgerService
from app.service.stored_value.member import MemberBalanceService

MOBILE = "13800001000"


@pytest.fixture
async def asset_db(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """每个用例独享文件数据库，支持多连接并发。"""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "asset-atomic.db"))
    connection = await init_db(settings.DB_PATH)
    await close_db(connection)
    yield


def _member_service() -> MemberBalanceService:
    """使用当前事务连接的储值服务。"""
    return MemberBalanceService()


def _points_service() -> PointsLedgerService:
    """使用当前事务连接的积分服务。"""
    return PointsLedgerService()


async def _stored_balance(mobile: str = MOBILE) -> int:
    async with db_session_scope():
        return await MemberBalanceRepo().get_stored_value_fen(mobile)


async def _points_balance(mobile: str = MOBILE) -> int:
    async with db_session_scope():
        return await MemberBalanceRepo().get_points(mobile)


async def _ledger_count(table: str, mobile: str = MOBILE) -> int:
    """按表统计手机号流水数。"""
    if table == "balance_ledger":
        sql = "SELECT COUNT(*) AS c FROM balance_ledger WHERE mobile = ?"
    elif table == "points_ledger":
        sql = "SELECT COUNT(*) AS c FROM points_ledger WHERE mobile = ?"
    else:
        raise ValueError(f"未知账本表 {table}")
    async with db_session_scope():
        rows = await MemberBalanceRepo()._db.execute_fetchall(sql, (mobile,))
        return int(rows[0]["c"])


@pytest.mark.asyncio
async def test_stored_credit_replay_applies_once(asset_db) -> None:
    """储值重复加款只应用一次，流水唯一。"""
    async with db_session_scope():
        first = await _member_service().credit(
            user_id="u1",
            mobile=MOBILE,
            amount_fen=100,
            biz_type="recharge",
            biz_id="b1",
            unique_id="sv-credit-1",
            source="recharge",
        )
        second = await _member_service().credit(
            user_id="u1",
            mobile=MOBILE,
            amount_fen=100,
            biz_type="recharge",
            biz_id="b1",
            unique_id="sv-credit-1",
            source="recharge",
        )
    assert (first, second) == (100, 100)
    assert await _stored_balance() == 100
    assert await _ledger_count("balance_ledger") == 1


@pytest.mark.asyncio
async def test_stored_credit_key_amount_mismatch_rejected(asset_db) -> None:
    """同幂等键不同金额直接拒绝，余额不受影响。"""
    async with db_session_scope():
        await _member_service().credit(
            user_id="u1",
            mobile=MOBILE,
            amount_fen=100,
            biz_type="recharge",
            biz_id="b1",
            unique_id="sv-credit-2",
            source="recharge",
        )
        with pytest.raises(ValueError, match="幂等键金额冲突"):
            await _member_service().credit(
                user_id="u1",
                mobile=MOBILE,
                amount_fen=200,
                biz_type="recharge",
                biz_id="b1",
                unique_id="sv-credit-2",
                source="recharge",
            )
    assert await _stored_balance() == 100
    assert await _ledger_count("balance_ledger") == 1


@pytest.mark.asyncio
async def test_stored_deduct_replay_applies_once(asset_db) -> None:
    """储值重复扣款只应用一次，流水唯一。"""
    async with db_session_scope():
        await _member_service().credit(
            user_id="u1",
            mobile=MOBILE,
            amount_fen=100,
            biz_type="recharge",
            biz_id="b0",
            unique_id="sv-seed-1",
            source="recharge",
        )
        first = await _member_service().deduct(
            user_id="u1",
            mobile=MOBILE,
            amount_fen=40,
            biz_type="order_pay",
            biz_id="o1",
            unique_id="sv-deduct-1",
            source="order",
        )
        second = await _member_service().deduct(
            user_id="u1",
            mobile=MOBILE,
            amount_fen=40,
            biz_type="order_pay",
            biz_id="o1",
            unique_id="sv-deduct-1",
            source="order",
        )
    assert (first, second) == (60, 60)
    assert await _stored_balance() == 60
    assert await _ledger_count("balance_ledger") == 2


@pytest.mark.asyncio
async def test_stored_deduct_insufficient_leaves_no_trace(asset_db) -> None:
    """余额不足不扣款不记账。"""
    async with db_session_scope():
        await _member_service().credit(
            user_id="u1",
            mobile=MOBILE,
            amount_fen=30,
            biz_type="recharge",
            biz_id="b0",
            unique_id="sv-seed-2",
            source="recharge",
        )
        result = await _member_service().deduct(
            user_id="u1",
            mobile=MOBILE,
            amount_fen=80,
            biz_type="order_pay",
            biz_id="o2",
            unique_id="sv-deduct-2",
            source="order",
        )
    assert result is None
    assert await _stored_balance() == 30
    assert await _ledger_count("balance_ledger") == 1


@pytest.mark.asyncio
async def test_points_credit_and_deduct_idempotent(asset_db) -> None:
    """积分加款扣款重放幂等，同键异额拒绝。"""
    async with db_session_scope():
        assert (
            await _points_service().credit(
                mobile=MOBILE,
                amount=50,
                biz_type="order_award",
                biz_id="o1",
                unique_id="pt-credit-1",
                event_type="award",
            )
            == 50
        )
        assert (
            await _points_service().credit(
                mobile=MOBILE,
                amount=50,
                biz_type="order_award",
                biz_id="o1",
                unique_id="pt-credit-1",
                event_type="award",
            )
            == 50
        )
        with pytest.raises(ValueError, match="幂等键金额冲突"):
            await _points_service().credit(
                mobile=MOBILE,
                amount=60,
                biz_type="order_award",
                biz_id="o1",
                unique_id="pt-credit-1",
                event_type="award",
            )
        assert (
            await _points_service().deduct(
                mobile=MOBILE,
                amount=20,
                biz_type="order_redeem",
                biz_id="o2",
                unique_id="pt-deduct-1",
                event_type="redeem",
            )
            == 30
        )
        assert (
            await _points_service().deduct(
                mobile=MOBILE,
                amount=20,
                biz_type="order_redeem",
                biz_id="o2",
                unique_id="pt-deduct-1",
                event_type="redeem",
            )
            == 30
        )
        assert (
            await _points_service().deduct(
                mobile=MOBILE,
                amount=100,
                biz_type="order_redeem",
                biz_id="o3",
                unique_id="pt-deduct-2",
                event_type="redeem",
            )
            is None
        )
    assert await _points_balance() == 30
    assert await _ledger_count("points_ledger") == 2


@pytest.mark.asyncio
async def test_concurrent_deducts_single_winner(asset_db) -> None:
    """两连接并发扣款仅一笔成功，无负余额且流水一致。"""
    async with db_session_scope():
        await _member_service().credit(
            user_id="u1",
            mobile=MOBILE,
            amount_fen=100,
            biz_type="recharge",
            biz_id="b0",
            unique_id="sv-seed-3",
            source="recharge",
        )
    barrier = asyncio.Barrier(2)

    async def attempt(unique_id: str):
        async with db_session_scope():
            await barrier.wait()
            return await _member_service().deduct(
                user_id="u1",
                mobile=MOBILE,
                amount_fen=80,
                biz_type="order_pay",
                biz_id=unique_id,
                unique_id=unique_id,
                source="order",
            )

    first, second = await asyncio.gather(attempt("sv-race-1"), attempt("sv-race-2"))
    assert sorted([first is not None, second is not None]) == [False, True]
    assert await _stored_balance() == 20
    assert await _ledger_count("balance_ledger") == 2


@pytest.mark.asyncio
async def test_credit_failure_rolls_back_without_orphan(
    asset_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """流水补写失败整体回滚，不存在孤立余额变更。"""
    from app.repository import balance_ledger_repo as ledger_module

    async def failing_complete(self, unique_id: str, balance_after_fen: int) -> None:
        raise RuntimeError("模拟流水补写失败")

    monkeypatch.setattr(
        ledger_module.BalanceLedgerRepo, "complete_placeholder", failing_complete
    )
    with pytest.raises(RuntimeError, match="模拟流水补写失败"):
        async with db_session_scope():
            await _member_service().credit(
                user_id="u1",
                mobile=MOBILE,
                amount_fen=100,
                biz_type="recharge",
                biz_id="b9",
                unique_id="sv-fail-1",
                source="recharge",
            )
    assert await _stored_balance() == 0
    assert await _ledger_count("balance_ledger") == 0


@pytest.mark.asyncio
async def test_points_and_balance_independent_ledgers(asset_db) -> None:
    """储值与积分流水相互独立，余额互不干扰。"""
    async with db_session_scope():
        await _member_service().credit(
            user_id="u1",
            mobile=MOBILE,
            amount_fen=100,
            biz_type="recharge",
            biz_id="b0",
            unique_id="sv-seed-4",
            source="recharge",
        )
        await _points_service().credit(
            mobile=MOBILE,
            amount=40,
            biz_type="order_award",
            biz_id="o1",
            unique_id="pt-seed-4",
            event_type="award",
        )
    assert await _stored_balance() == 100
    assert await _points_balance() == 40
    assert await _ledger_count("balance_ledger") == 1
    assert await _ledger_count("points_ledger") == 1


def test_accounting_services_own_their_transaction() -> None:
    """静态检查：记账方法必须显式持有事务边界。"""
    from pathlib import Path

    for rel in (
        "app/service/stored_value/member.py",
        "app/service/points/ledger.py",
    ):
        content = (Path(__file__).resolve().parents[2] / rel).read_text(
            encoding="utf-8"
        )
        assert "transaction()" in content
        assert "insert_placeholder" in content
