"""知识库发布治理字段迁移测试。"""

import aiosqlite

from app.migrations.runner import run_migrations


async def test_knowledge_governance_columns_created(
    db: aiosqlite.Connection,
) -> None:
    """初始化数据库后应包含知识库发布治理字段。"""
    columns = await _column_names(db, "knowledge_base")

    assert {
        "audience",
        "review_status",
        "valid_from",
        "valid_until",
        "reviewed_by",
        "reviewed_at",
    }.issubset(columns)


async def test_knowledge_governance_index_created(
    db: aiosqlite.Connection,
) -> None:
    """初始化数据库后应包含知识库治理检索索引。"""
    indexes = await _index_names(db, "knowledge_base")

    assert "idx_kb_governance_lookup" in indexes


async def test_knowledge_governance_migration_idempotent(
    db: aiosqlite.Connection,
) -> None:
    """版本化迁移重复执行时不应再次应用。"""
    applied_count = await run_migrations(db)
    rows = await db.execute_fetchall(
        "SELECT version FROM _schema_version WHERE version = ?",
        (15,),
    )

    assert applied_count == 0
    assert rows[0]["version"] == 15


async def test_knowledge_retrieval_logs_table_created(
    db: aiosqlite.Connection,
) -> None:
    """初始化数据库后应包含知识检索命中日志表和索引。"""
    columns = await _column_names(db, "knowledge_retrieval_logs")
    indexes = await _index_names(db, "knowledge_retrieval_logs")

    assert {
        "bot_type",
        "audience",
        "query",
        "retrieval_mode",
        "matched_entry_ids_json",
        "matched_titles_json",
        "result_count",
        "fallback_reason",
        "created_at",
    }.issubset(columns)
    assert "idx_krl_created_at" in indexes
    assert "idx_krl_bot_audience_created" in indexes


async def test_knowledge_retrieval_logs_migration_idempotent(
    db: aiosqlite.Connection,
) -> None:
    """v016 重复执行时不应再次应用。"""
    applied_count = await run_migrations(db)
    rows = await db.execute_fetchall(
        "SELECT version FROM _schema_version WHERE version = ?",
        (16,),
    )

    assert applied_count == 0
    assert rows[0]["version"] == 16


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
