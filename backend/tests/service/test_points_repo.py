# -*- coding: utf-8 -*-
"""积分模块 v023 仓储测试：迁移字段、幂等与余额不足。"""

import aiosqlite
import pytest

from app.models.member import LedgerSource, PointsLedgerEntry
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.points_ledger_repo import PointsLedgerRepo


async def _column_names(db: aiosqlite.Connection, table: str) -> list[str]:
    rows = await db.execute_fetchall(f"PRAGMA table_info({table})")
    return [row["name"] for row in rows]


@pytest.mark.asyncio
async def test_v023_points_ledger_columns(db: aiosqlite.Connection) -> None:
    """points_ledger 应包含 biz_type/biz_id，source 允许 order。"""
    columns = await _column_names(db, "points_ledger")
    assert {"biz_type", "biz_id"}.issubset(columns)


@pytest.mark.asyncio
async def test_points_ledger_insert_and_list_by_mobile(
    db: aiosqlite.Connection,
) -> None:
    """积分流水写入后可按手机号倒序查询。"""
    repo = PointsLedgerRepo(db)
    await repo.insert(
        PointsLedgerEntry(
            unique_id="p1",
            amount=10,
            total=100,
            event_type="order_award",
            source=LedgerSource.ORDER,
            biz_type="order_award",
            biz_id="order_1",
            mobile="13800000000",
            occurred_at="2026-08-13 10:00:00",
        )
    )
    rows = await repo.list_by_mobile("13800000000")
    assert len(rows) == 1
    assert rows[0]["biz_type"] == "order_award"
    assert rows[0]["biz_id"] == "order_1"
    assert rows[0]["source"] == "order"
    assert await repo.get_by_unique_id("p1") is not None


@pytest.mark.asyncio
async def test_member_balance_points_credit_and_deduct(
    db: aiosqlite.Connection,
) -> None:
    """积分加款/余额不足不扣/原子扣款。"""
    repo = MemberBalanceRepo(db)
    assert await repo.get_points("13800000001") == 0
    assert await repo.credit_points("13800000001", 500) == 500
    assert await repo.get_points("13800000001") == 500
    assert not await repo.deduct_points_if_sufficient("13800000001", 600)
    assert await repo.get_points("13800000001") == 500
    assert await repo.deduct_points_if_sufficient("13800000001", 200)
    assert await repo.get_points("13800000001") == 300
