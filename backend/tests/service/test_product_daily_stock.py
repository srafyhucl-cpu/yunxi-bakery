"""每日现烤库存服务测试。"""

import aiosqlite
import pytest

from app.repository.product_daily_stock_repo import ProductDailyStockRepo
from app.service.catalog.daily_stock import ProductDailyStockService

STOCK_DATE = "2026-10-20"
PREVIOUS_DATE = "2026-10-19"


async def test_ensure_date_copies_previous_day(db: aiosqlite.Connection) -> None:
    """当天没有记录时复制之前最近一天，且只复制一次。"""
    repo = ProductDailyStockRepo(db)
    await repo.upsert_total(PREVIOUS_DATE, "101", 6, "admin")
    await repo.reserve("101", PREVIOUS_DATE, 2)
    service = ProductDailyStockService(repo)

    copied = await service.ensure_date(STOCK_DATE)
    repeated = await service.ensure_date(STOCK_DATE)

    assert copied == 1
    assert repeated == 0
    row = await repo.get_for_date("101", STOCK_DATE)
    assert row["total_qty"] == 6
    assert row["reserved_qty"] == 0


async def test_ensure_date_fills_missing_products_on_partial_day(
    db: aiosqlite.Connection,
) -> None:
    """当天已有部分商品时，仍应从昨日补齐缺失商品且保留今日已有总量。"""
    repo = ProductDailyStockRepo(db)
    await repo.upsert_total(PREVIOUS_DATE, "A", 6, "admin")
    await repo.upsert_total(PREVIOUS_DATE, "B", 4, "admin")
    await repo.upsert_total(STOCK_DATE, "A", 2, "manager")
    service = ProductDailyStockService(repo)

    copied = await service.ensure_date(STOCK_DATE)

    assert copied == 1
    first = await repo.get_for_date("A", STOCK_DATE)
    second = await repo.get_for_date("B", STOCK_DATE)
    assert first["total_qty"] == 2
    assert first["updated_by"] == "manager"
    assert second["total_qty"] == 4
    assert second["reserved_qty"] == 0
    assert second["updated_by"] == "system_copy"


async def test_set_total_rejects_below_reserved(db: aiosqlite.Connection) -> None:
    """后台录入总量低于已预占数量时必须拒绝。"""
    repo = ProductDailyStockRepo(db)
    service = ProductDailyStockService(repo)
    await service.set_total(STOCK_DATE, "101", 5, "admin")
    await service.reserve("101", STOCK_DATE, 3)

    with pytest.raises(ValueError, match="不能低于已预占"):
        await service.set_total(STOCK_DATE, "101", 2, "admin")

    row = await repo.get_for_date("101", STOCK_DATE)
    assert row["total_qty"] == 5
    assert await service.set_total(STOCK_DATE, "101", 3, "admin") is True


async def test_invalid_stock_date_raises(db: aiosqlite.Connection) -> None:
    """非法日期必须在进入数据库前被拒绝。"""
    service = ProductDailyStockService(ProductDailyStockRepo(db))

    for value in ("2026-13-01", "2026/10/20", "", "20261020"):
        with pytest.raises(ValueError, match="库存日期格式无效"):
            await service.ensure_date(value)
