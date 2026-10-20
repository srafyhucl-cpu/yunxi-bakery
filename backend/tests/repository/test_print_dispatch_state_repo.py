"""打印调度游标仓库测试。"""

import aiosqlite

from app.repository.print_dispatch_state_repo import PrintDispatchStateRepo


async def test_get_or_create_is_idempotent(db: aiosqlite.Connection) -> None:
    """首次创建后重复读取不再覆盖初始游标。"""
    repo = PrintDispatchStateRepo(db)

    first = await repo.get_or_create("2026-01-01 00:00:00")
    second = await repo.get_or_create("2026-02-02 00:00:00")

    assert first["id"] == "default"
    assert first["last_updated_at"] == "2026-01-01 00:00:00"
    assert first["last_order_id"] == ""
    assert second["last_updated_at"] == "2026-01-01 00:00:00"
    assert second["last_order_id"] == ""
    rows = await db.execute_fetchall(
        "SELECT COUNT(*) AS total FROM order_print_dispatch_state"
    )
    assert rows[0]["total"] == 1


async def test_set_cursor_updates_single_row(db: aiosqlite.Connection) -> None:
    """推进游标只更新固定单行。"""
    repo = PrintDispatchStateRepo(db)
    await repo.get_or_create("2026-01-01 00:00:00")

    await repo.set_cursor("2026-10-19 10:00:00", "order_100")
    cursor = await repo.get_or_create("2026-01-01 00:00:00")

    assert cursor["last_updated_at"] == "2026-10-19 10:00:00"
    assert cursor["last_order_id"] == "order_100"
    assert cursor["updated_at"]
