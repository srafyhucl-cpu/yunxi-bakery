"""有赞 webhook 审计表 business_type 放开 member 的迁移测试。"""

import sqlite3
from pathlib import Path

import aiosqlite
import pytest

from app.migrations.runner import _split_sql_statements, run_migrations

MIGRATION_FILE = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "migrations"
    / "v048_youzan_webhook_member_business_type.sql"
)

# 迁移前的历史表结构：business_type 的 CHECK 不含 member
LEGACY_TABLE_DDL = """CREATE TABLE youzan_webhook_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id TEXT NOT NULL UNIQUE,
    trace_id TEXT DEFAULT '',
    event_type TEXT DEFAULT '',
    business_type TEXT NOT NULL
        CHECK(business_type IN ('trade','item','chat','unknown')),
    business_key TEXT DEFAULT '',
    status TEXT NOT NULL
        CHECK(status IN ('received','processing','processed','skipped','failed','duplicate')),
    http_status INTEGER DEFAULT 200,
    process_stage TEXT DEFAULT '',
    error_type TEXT DEFAULT '',
    error_message TEXT DEFAULT '',
    payload_hash TEXT DEFAULT '',
    payload_summary_json TEXT DEFAULT '{}',
    received_at TEXT NOT NULL,
    process_started_at TEXT,
    process_finished_at TEXT,
    duration_ms INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
)"""

LEGACY_INDEX_DDL = (
    "CREATE INDEX idx_ywe_received ON youzan_webhook_events(received_at)",
    "CREATE INDEX idx_ywe_status ON youzan_webhook_events(status)",
    "CREATE INDEX idx_ywe_event_type ON youzan_webhook_events(event_type)",
    "CREATE INDEX idx_ywe_business_key ON youzan_webhook_events(business_key)",
)

EXPECTED_INDEXES = {
    "idx_ywe_received",
    "idx_ywe_status",
    "idx_ywe_event_type",
    "idx_ywe_business_key",
}


async def test_v048_keeps_legacy_audit_rows(db: aiosqlite.Connection) -> None:
    """迁移后历史审计数据应完整保留。"""
    await _create_legacy_table(db)
    for business_type in ("trade", "item", "chat", "unknown"):
        await db.execute(
            "INSERT INTO youzan_webhook_events "
            "(msg_id, business_type, business_key, status, received_at) "
            "VALUES (?, ?, ?, 'processed', '2026-10-20 10:00:00')",
            (f"yzmsg_{business_type}", business_type, f"key_{business_type}"),
        )
    await db.commit()

    await _apply_v048(db)

    rows = await db.execute_fetchall(
        "SELECT msg_id, business_type, business_key, status FROM "
        "youzan_webhook_events ORDER BY msg_id"
    )
    assert len(rows) == 4
    assert {row["business_type"] for row in rows} == {
        "trade",
        "item",
        "chat",
        "unknown",
    }
    assert {row["status"] for row in rows} == {"processed"}


async def test_v048_allows_member_business_type(db: aiosqlite.Connection) -> None:
    """迁移后应能写入 member 类型的审计记录。"""
    await _create_legacy_table(db)
    await _apply_v048(db)

    await db.execute(
        "INSERT INTO youzan_webhook_events "
        "(msg_id, business_type, status, received_at) "
        "VALUES ('yzuser_abc', 'member', 'processed', '2026-10-20 10:00:00')"
    )
    await db.commit()

    rows = await db.execute_fetchall(
        "SELECT business_type FROM youzan_webhook_events WHERE msg_id = ?",
        ("yzuser_abc",),
    )
    assert rows[0]["business_type"] == "member"


async def test_v048_rejects_invalid_business_type(db: aiosqlite.Connection) -> None:
    """迁移后非法 business_type 仍应被 CHECK 约束拒绝。"""
    await _create_legacy_table(db)
    await _apply_v048(db)

    with pytest.raises(sqlite3.IntegrityError):
        await db.execute(
            "INSERT INTO youzan_webhook_events "
            "(msg_id, business_type, status, received_at) "
            "VALUES ('yzuser_bad', 'bogus', 'processed', '2026-10-20 10:00:00')"
        )
    await db.rollback()


async def test_v048_recreates_indexes(db: aiosqlite.Connection) -> None:
    """迁移后原有索引应被完整重建。"""
    await _create_legacy_table(db)
    await _apply_v048(db)

    indexes = await _index_names(db, "youzan_webhook_events")

    assert EXPECTED_INDEXES.issubset(indexes)


async def test_v048_reapply_keeps_data(db: aiosqlite.Connection) -> None:
    """迁移重复执行时数据不应丢失，且 member 依旧可写。"""
    await _create_legacy_table(db)
    await db.execute(
        "INSERT INTO youzan_webhook_events "
        "(msg_id, business_type, status, received_at) "
        "VALUES ('yzmsg_trade', 'trade', 'processed', '2026-10-20 10:00:00')"
    )
    await db.commit()

    await _apply_v048(db)
    await _apply_v048(db)

    rows = await db.execute_fetchall(
        "SELECT msg_id, business_type FROM youzan_webhook_events"
    )
    assert [tuple(row) for row in rows] == [("yzmsg_trade", "trade")]

    await db.execute(
        "INSERT INTO youzan_webhook_events "
        "(msg_id, business_type, status, received_at) "
        "VALUES ('yzuser_again', 'member', 'processed', '2026-10-20 10:00:01')"
    )
    await db.commit()


async def test_v048_supports_table_with_member_constraint(
    db: aiosqlite.Connection,
) -> None:
    """表结构已含 member 的新库再执行迁移也应正常完成。"""
    await _apply_v048(db)
    await _apply_v048(db)

    await db.execute(
        "INSERT INTO youzan_webhook_events "
        "(msg_id, business_type, status, received_at) "
        "VALUES ('yzuser_new', 'member', 'processed', '2026-10-20 10:00:00')"
    )
    await db.commit()


async def test_runner_reapplies_v048_on_legacy_database(
    db: aiosqlite.Connection,
) -> None:
    """走真实迁移执行器时，旧库补跑 v048 后应放开 member 约束。"""
    await _create_legacy_table(db)
    await db.execute(
        "INSERT INTO youzan_webhook_events "
        "(msg_id, business_type, status, received_at) "
        "VALUES ('yzmsg_trade', 'trade', 'processed', '2026-10-20 10:00:00')"
    )
    await db.execute("DELETE FROM _schema_version WHERE version = 48")
    await db.commit()

    applied_count = await run_migrations(db)

    assert applied_count == 1
    await db.execute(
        "INSERT INTO youzan_webhook_events "
        "(msg_id, business_type, status, received_at) "
        "VALUES ('yzuser_runner', 'member', 'processed', '2026-10-20 10:00:01')"
    )
    await db.commit()
    rows = await db.execute_fetchall(
        "SELECT msg_id, business_type FROM youzan_webhook_events ORDER BY msg_id"
    )
    assert [tuple(row) for row in rows] == [
        ("yzmsg_trade", "trade"),
        ("yzuser_runner", "member"),
    ]
    indexes = await _index_names(db, "youzan_webhook_events")
    assert EXPECTED_INDEXES.issubset(indexes)


async def test_new_database_accepts_member_business_type(
    db: aiosqlite.Connection,
) -> None:
    """全新建库后应可直接写入 member 类型审计记录。"""
    await db.execute(
        "INSERT INTO youzan_webhook_events "
        "(msg_id, business_type, status, received_at) "
        "VALUES ('yzuser_fresh', 'member', 'processed', '2026-10-20 10:00:00')"
    )
    await db.commit()

    rows = await db.execute_fetchall(
        "SELECT business_type FROM youzan_webhook_events WHERE msg_id = ?",
        ("yzuser_fresh",),
    )
    assert rows[0]["business_type"] == "member"

    table_sql = await db.execute_fetchall(
        "SELECT sql FROM sqlite_master WHERE name = 'youzan_webhook_events'"
    )
    assert "'member'" in table_sql[0]["sql"]


async def _create_legacy_table(db: aiosqlite.Connection) -> None:
    """建出迁移前的历史表结构（含原索引）。"""
    await db.execute("DROP TABLE IF EXISTS youzan_webhook_events")
    await db.execute(LEGACY_TABLE_DDL)
    for index_ddl in LEGACY_INDEX_DDL:
        await db.execute(index_ddl)
    await db.commit()


async def _apply_v048(db: aiosqlite.Connection) -> None:
    """按迁移执行器的方式逐条执行 v048 迁移脚本。"""
    sql_content = MIGRATION_FILE.read_text(encoding="utf-8")
    for stmt in _split_sql_statements(sql_content):
        if not stmt.strip():
            continue
        await db.execute(stmt)
    await db.commit()


async def _index_names(db: aiosqlite.Connection, table_name: str) -> set[str]:
    rows = await db.execute_fetchall(
        "SELECT name FROM pragma_index_list(?)",
        (table_name,),
    )
    return {row["name"] for row in rows}
