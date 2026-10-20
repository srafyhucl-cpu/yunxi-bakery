"""定制蛋糕时段容量表结构迁移测试。"""

import sqlite3

import aiosqlite
import pytest


async def test_cake_slot_tables_and_indexes(db: aiosqlite.Connection) -> None:
    """初始化后应包含容量表、预占表与时段索引。"""
    capacity_columns = await _column_names(db, "cake_slot_capacity")
    reservation_columns = await _column_names(db, "cake_slot_reservations")
    reservation_indexes = await _index_names(db, "cake_slot_reservations")

    assert capacity_columns == {"slot_key", "reserved_count", "updated_at"}
    assert reservation_columns == {"order_id", "slot_key", "created_at"}
    assert "idx_cake_slot_reservations_slot" in reservation_indexes


async def test_cake_slot_capacity_rejects_negative_count(
    db: aiosqlite.Connection,
) -> None:
    """容量表必须拒绝负数预占量。"""
    with pytest.raises(sqlite3.IntegrityError):
        await db.execute(
            "INSERT INTO cake_slot_capacity (slot_key, reserved_count, updated_at) "
            "VALUES ('2026-10-20 14:00-16:00', -1, 'now')"
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
