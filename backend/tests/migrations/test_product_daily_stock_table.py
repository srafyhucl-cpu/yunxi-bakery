"""每日现烤库存表结构迁移测试。"""

import sqlite3

import aiosqlite
import pytest


async def test_product_daily_stock_table_and_indexes(db: aiosqlite.Connection) -> None:
    """初始化后应包含每日库存表、关键字段与日期/商品索引。"""
    columns = await _column_names(db, "product_daily_stock")
    indexes = await _index_names(db, "product_daily_stock")

    assert {
        "stock_date",
        "product_id",
        "total_qty",
        "reserved_qty",
        "updated_by",
        "created_at",
        "updated_at",
    }.issubset(columns)
    assert "idx_pds_stock_date" in indexes
    assert "idx_pds_product_id" in indexes


async def test_product_daily_stock_rejects_invalid_quantities(
    db: aiosqlite.Connection,
) -> None:
    """预占量超过总量或出现负数时，数据库约束必须拒绝。"""
    with pytest.raises(sqlite3.IntegrityError):
        await db.execute(
            "INSERT INTO product_daily_stock ("
            "stock_date, product_id, total_qty, reserved_qty, created_at, updated_at"
            ") VALUES ('2026-10-20', '101', 1, 2, 'now', 'now')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        await db.execute(
            "INSERT INTO product_daily_stock ("
            "stock_date, product_id, total_qty, reserved_qty, created_at, updated_at"
            ") VALUES ('2026-10-20', '102', -1, 0, 'now', 'now')"
        )


async def _column_names(db: aiosqlite.Connection, table_name: str) -> set[str]:
    rows = await db.execute_fetchall(
        "SELECT name FROM pragma_table_info(?)",
        (table_name,),
    )
    return {row["name"] for row in rows}


async def _index_names(db: aiosqlite.Connection, table_name: str) -> set[str]:
    rows = await db.execute_fetchall(
        "SELECT name FROM pragma_index_list(?)",
        (table_name,),
    )
    return {row["name"] for row in rows}
