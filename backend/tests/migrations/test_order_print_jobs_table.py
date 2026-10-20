"""订单打印作业表结构迁移测试。"""

import sqlite3

import aiosqlite
import pytest

EXPECTED_COLUMNS = {
    "id",
    "order_id",
    "ticket_type",
    "status",
    "provider",
    "printer_id",
    "attempts",
    "last_error",
    "provider_job_id",
    "idempotency_key",
    "payload_snapshot",
    "operator",
    "created_at",
    "updated_at",
    "printed_at",
}


async def test_order_print_jobs_table_and_indexes(db: aiosqlite.Connection) -> None:
    """初始化后应包含完整字段、订单/状态索引与幂等唯一约束。"""
    assert await _column_names(db, "order_print_jobs") == EXPECTED_COLUMNS
    indexes = await _index_names(db, "order_print_jobs")
    assert "idx_order_print_jobs_order_id" in indexes
    assert "idx_order_print_jobs_status" in indexes


async def test_order_print_jobs_rejects_invalid_ticket_type_and_status(
    db: aiosqlite.Connection,
) -> None:
    """联单类型与状态必须命中 CHECK 约束。"""
    with pytest.raises(sqlite3.IntegrityError):
        await _insert(db, ticket_type="UNKNOWN", status="PENDING")
    with pytest.raises(sqlite3.IntegrityError):
        await _insert(db, ticket_type="CAKE_KITCHEN", status="UNKNOWN")


async def test_order_print_jobs_idempotency_key_is_unique(
    db: aiosqlite.Connection,
) -> None:
    """相同幂等键不能写入第二条作业。"""
    await _insert(db, ticket_type="CAKE_KITCHEN", status="PENDING")
    with pytest.raises(sqlite3.IntegrityError):
        await _insert(db, ticket_type="DAILY_FRONT", status="PENDING")


async def _insert(
    db: aiosqlite.Connection,
    *,
    ticket_type: str,
    status: str,
) -> None:
    await db.execute(
        "INSERT INTO order_print_jobs ("
        "id, order_id, ticket_type, status, provider, printer_id, attempts, "
        "last_error, provider_job_id, idempotency_key, payload_snapshot, operator, "
        "created_at, updated_at, printed_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "job_1",
            "order_1",
            ticket_type,
            status,
            "mock",
            "",
            0,
            "",
            "",
            "order:order_1:CAKE_KITCHEN:v1",
            "",
            "tester",
            "2026-10-19 10:00:00",
            "2026-10-19 10:00:00",
            "",
        ),
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
