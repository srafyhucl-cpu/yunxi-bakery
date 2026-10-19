"""打印调度游标表结构迁移测试。"""

import sqlite3

import aiosqlite
import pytest

EXPECTED_COLUMNS = {
    "id",
    "last_updated_at",
    "last_order_id",
    "updated_at",
}


async def test_print_dispatch_state_table_and_primary_key(
    db: aiosqlite.Connection,
) -> None:
    """初始化后应包含游标表字段，且 id 为唯一主键。"""
    rows = await db.execute_fetchall(
        "SELECT name, pk FROM pragma_table_info(?)",
        ("order_print_dispatch_state",),
    )
    columns = {row["name"] for row in rows}
    primary_keys = {row["name"] for row in rows if row["pk"] == 1}

    assert columns == EXPECTED_COLUMNS
    assert primary_keys == {"id"}


async def test_print_dispatch_state_rejects_duplicate_default_row(
    db: aiosqlite.Connection,
) -> None:
    """固定单行主键阻止写入第二份游标。"""
    await db.execute(
        "INSERT INTO order_print_dispatch_state "
        "(id, last_updated_at, last_order_id, updated_at) "
        "VALUES ('default', '', '', '2026-10-19 10:00:00')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        await db.execute(
            "INSERT INTO order_print_dispatch_state "
            "(id, last_updated_at, last_order_id, updated_at) "
            "VALUES ('default', '', '', '2026-10-19 10:01:00')"
        )
