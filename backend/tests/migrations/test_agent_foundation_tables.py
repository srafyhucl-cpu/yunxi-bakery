"""Agent 化 P0 基础表迁移测试。"""

import aiosqlite

from app.migrations.runner import run_migrations


async def test_agent_foundation_tables_created(db: aiosqlite.Connection) -> None:
    """初始化数据库后应包含 P0 三张新表和关键字段。"""
    profile_columns = await _column_names(db, "customer_profiles")
    review_columns = await _column_names(db, "conversation_reviews")
    gap_columns = await _column_names(db, "knowledge_gaps")

    assert {
        "channel",
        "user_id",
        "preferences_json",
        "allergens_json",
        "source_evidence_json",
    }.issubset(profile_columns)
    assert {"session_id", "quality_score", "issues_json"}.issubset(review_columns)
    assert {"question_norm", "frequency", "status"}.issubset(gap_columns)


async def test_agent_foundation_indexes_created(db: aiosqlite.Connection) -> None:
    """初始化数据库后应包含 P0 设计要求的索引。"""
    profile_indexes = await _index_names(db, "customer_profiles")
    review_indexes = await _index_names(db, "conversation_reviews")
    gap_indexes = await _index_names(db, "knowledge_gaps")

    assert "idx_cp_channel_user" in profile_indexes
    assert "idx_cr_session" in review_indexes
    assert "idx_cr_score" in review_indexes
    assert "idx_kg_status" in gap_indexes
    assert "idx_kg_freq" in gap_indexes


async def test_agent_foundation_migration_idempotent(
    db: aiosqlite.Connection,
) -> None:
    """版本化迁移重复执行时不应再次应用。"""
    applied_count = await run_migrations(db)
    rows = await db.execute_fetchall(
        "SELECT version FROM _schema_version WHERE version = ?",
        (4,),
    )

    assert applied_count == 0
    assert rows[0]["version"] == 4


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
