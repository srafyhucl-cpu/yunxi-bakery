"""每日现烤库存仓库测试。"""

import asyncio

import aiosqlite

from app.repository.product_daily_stock_repo import ProductDailyStockRepo

STOCK_DATE = "2026-10-20"


async def test_reserve_and_release_are_atomic(db: aiosqlite.Connection) -> None:
    """预占累加、库存不足拒绝、释放回补且不产生负数。"""
    repo = ProductDailyStockRepo(db)
    await repo.upsert_total(STOCK_DATE, "101", 5, "admin")

    assert await repo.reserve("101", STOCK_DATE, 2) is True
    row = await repo.get_for_date("101", STOCK_DATE)
    assert row is not None
    assert row["reserved_qty"] == 2

    assert await repo.reserve("101", STOCK_DATE, 4) is False
    row = await repo.get_for_date("101", STOCK_DATE)
    assert row["reserved_qty"] == 2

    assert await repo.release("101", STOCK_DATE, 5) is True
    row = await repo.get_for_date("101", STOCK_DATE)
    assert row["reserved_qty"] == 0


async def test_upsert_total_rejects_below_reserved(db: aiosqlite.Connection) -> None:
    """录入总量不能低于已预占，合法更新仍可写入。"""
    repo = ProductDailyStockRepo(db)
    await repo.upsert_total(STOCK_DATE, "101", 5, "admin")
    await repo.reserve("101", STOCK_DATE, 3)

    assert await repo.upsert_total(STOCK_DATE, "101", 2, "admin") is False
    row = await repo.get_for_date("101", STOCK_DATE)
    assert row["total_qty"] == 5
    assert row["updated_by"] == "admin"

    assert await repo.upsert_total(STOCK_DATE, "101", 3, "manager") is True
    row = await repo.get_for_date("101", STOCK_DATE)
    assert row["total_qty"] == 3
    assert row["updated_by"] == "manager"


async def test_copy_from_previous_date_only_fills_missing_rows(
    db: aiosqlite.Connection,
) -> None:
    """跨日复制取最近一天总量，预占清零，已有目标行不被覆盖。"""
    repo = ProductDailyStockRepo(db)
    await repo.upsert_total("2026-10-18", "101", 8, "admin")
    await repo.upsert_total("2026-10-18", "102", 3, "admin")
    await repo.upsert_total("2026-10-17", "103", 99, "admin")
    await repo.upsert_total(STOCK_DATE, "101", 2, "manager")

    copied = await repo.copy_from_previous_date(STOCK_DATE)

    assert copied == 1
    first = await repo.get_for_date("101", STOCK_DATE)
    second = await repo.get_for_date("102", STOCK_DATE)
    assert first["total_qty"] == 2
    assert first["updated_by"] == "manager"
    assert second["total_qty"] == 3
    assert second["reserved_qty"] == 0
    assert second["updated_by"] == "system_copy"


async def test_concurrent_last_stock_only_one_succeeds(
    db: aiosqlite.Connection,
) -> None:
    """两个并发请求争抢最后一份库存时只能有一个成功。"""
    repo = ProductDailyStockRepo(db)
    await repo.upsert_total(STOCK_DATE, "101", 1, "admin")

    results = await asyncio.gather(
        repo.reserve("101", STOCK_DATE, 1),
        repo.reserve("101", STOCK_DATE, 1),
    )

    assert sorted(results) == [False, True]
    row = await repo.get_for_date("101", STOCK_DATE)
    assert row["reserved_qty"] == 1
