"""客户会话短期摘要表结构测试。"""

import aiosqlite

from app.migrations.runner import run_migrations


async def test_conversation_summary_table_created(
    db: aiosqlite.Connection,
) -> None:
    """初始化数据库后应包含会话摘要表和关键字段。"""
    columns = await _column_names(db, "conversation_summaries")

    assert {
        "session_id",
        "channel",
        "user_id",
        "summary_text",
        "state_json",
        "source_message_ids_json",
        "source_until_message_id",
        "token_estimate",
        "status",
    }.issubset(columns)


async def test_conversation_summary_indexes_created(
    db: aiosqlite.Connection,
) -> None:
    """初始化数据库后应包含会话摘要关键索引。"""
    indexes = await _index_names(db, "conversation_summaries")

    assert "idx_cs_session_status" in indexes
    assert "idx_cs_channel_user" in indexes
    assert "idx_cs_active_session" in indexes


async def test_conversation_summary_migration_idempotent(
    db: aiosqlite.Connection,
) -> None:
    """版本化迁移重复执行时不应再次应用。"""
    applied_count = await run_migrations(db)
    rows = await db.execute_fetchall(
        "SELECT version FROM _schema_version WHERE version = ?",
        (14,),
    )

    assert applied_count == 0
    assert rows[0]["version"] == 14


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
