from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
from types import ModuleType


def load_apply_migrations_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "apply_migrations.py"
    )
    spec = importlib.util.spec_from_file_location("apply_migrations", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _remove_late_migration_state(db_path: Path) -> None:
    with closing(sqlite3.connect(db_path)) as conn, conn:
        for table_name in (
            "customer_master",
            "customer_identity_links",
            "customer_source_snapshots",
            "customer_merge_reviews",
            "customer_profiles",
            "conversation_summaries",
            "knowledge_retrieval_logs",
            "customer_groups",
            "group_campaigns",
            "group_registrations",
            "conversation_reviews",
            "knowledge_gaps",
            "wecom_kf_sync_states",
            "wecom_kf_message_ledger",
        ):
            conn.execute("DROP TABLE IF EXISTS " + table_name)
        conn.execute(
            "DELETE FROM _schema_version WHERE version IN (?, ?, ?, ?, ?)",
            (4, 5, 14, 15, 16),
        )


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 6, 11, 12, 10, 0, tzinfo=tz)


async def test_run_migration_dry_run_does_not_create_database(tmp_path: Path) -> None:
    apply_migrations = load_apply_migrations_module()
    db_path = tmp_path / "missing" / "bot.db"

    report = await apply_migrations.run_migration(str(db_path), should_apply=False)

    assert report.applied is False
    assert db_path.exists() is False
    assert "customer_master" in report.missing_before
    assert "customer_profiles" in report.missing_before
    assert "conversation_summaries" in report.missing_before
    assert "knowledge_retrieval_logs" in report.missing_before
    assert "customer_groups" in report.missing_before
    assert report.missing_after == report.missing_before


async def test_run_migration_apply_creates_required_tables(tmp_path: Path) -> None:
    apply_migrations = load_apply_migrations_module()
    db_path = tmp_path / "bot.db"
    first_report = await apply_migrations.run_migration(
        str(db_path),
        should_apply=True,
        allow_create=True,
    )
    assert first_report.missing_after == []
    _remove_late_migration_state(db_path)

    report = await apply_migrations.run_migration(str(db_path), should_apply=True)

    assert report.applied is True
    assert "customer_master" in report.missing_before
    assert "customer_profiles" in report.missing_before
    assert "conversation_summaries" in report.missing_before
    assert "customer_groups" in report.missing_before
    assert report.missing_after == []


async def test_run_migration_apply_adds_missing_knowledge_governance_columns(
    tmp_path: Path,
) -> None:
    apply_migrations = load_apply_migrations_module()
    db_path = tmp_path / "bot.db"
    first_report = await apply_migrations.run_migration(
        str(db_path),
        should_apply=True,
        allow_create=True,
    )
    assert first_report.missing_after == []
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("ALTER TABLE knowledge_base RENAME TO knowledge_base_full")
        conn.execute(
            "CREATE TABLE knowledge_base (id INTEGER PRIMARY KEY, is_active INTEGER DEFAULT 1)"
        )
        conn.execute("DROP TABLE knowledge_base_full")
        conn.execute("DELETE FROM _schema_version WHERE version = ?", (15,))

    dry_run_report = await apply_migrations.run_migration(
        str(db_path),
        should_apply=False,
    )

    assert "knowledge_base.audience" in dry_run_report.missing_before

    apply_report = await apply_migrations.run_migration(
        str(db_path),
        should_apply=True,
    )

    assert apply_report.missing_after == []
    with closing(sqlite3.connect(db_path)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_base)")}
    assert {
        "audience",
        "review_status",
        "valid_from",
        "valid_until",
        "reviewed_by",
        "reviewed_at",
    }.issubset(columns)


async def test_init_db_applies_late_product_category_columns_to_old_database(
    tmp_path: Path,
) -> None:
    from app.database import close_db, init_db

    db_path = tmp_path / "bot.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            "CREATE TABLE youzan_products ("
            "item_id INTEGER PRIMARY KEY, "
            "title TEXT NOT NULL, "
            "alias TEXT NOT NULL UNIQUE, "
            "price_fen INTEGER NOT NULL, "
            "stock INTEGER NOT NULL, "
            "updated_at TEXT NOT NULL"
            ")"
        )
        conn.execute("CREATE TABLE _schema_version (version INTEGER PRIMARY KEY)")
        for version in range(1, 7):
            conn.execute("INSERT INTO _schema_version (version) VALUES (?)", (version,))

    db = await init_db(str(db_path))
    await close_db(db)

    with closing(sqlite3.connect(db_path)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(youzan_products)")}
        versions = {
            row[0] for row in conn.execute("SELECT version FROM _schema_version")
        }

    assert "tag_ids_json" in columns
    assert "classification_ids_json" in columns
    assert 11 in versions
    assert 13 in versions


async def test_async_main_returns_failure_for_dry_run_missing_tables(
    tmp_path: Path,
    capsys,
) -> None:
    apply_migrations = load_apply_migrations_module()
    db_path = tmp_path / "bot.db"

    exit_code = await apply_migrations.async_main(["--db-path", str(db_path)])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "mode=dry-run" in output
    assert "confirm target database path" in output
    assert "then rerun with --apply" in output


async def test_async_main_returns_success_after_apply(tmp_path: Path, capsys) -> None:
    apply_migrations = load_apply_migrations_module()
    db_path = tmp_path / "bot.db"

    exit_code = await apply_migrations.async_main(
        ["--db-path", str(db_path), "--apply", "--allow-create"]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "mode=apply" in output
    assert "allow_create=True" in output
    assert "missing_after=none" in output


def test_parse_args_help_mentions_dry_run_and_allow_create(capsys) -> None:
    apply_migrations = load_apply_migrations_module()

    try:
        apply_migrations.parse_args(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    help_text = capsys.readouterr().out
    assert "dry-run" in help_text
    assert "--allow-create" in help_text
    assert "--json" in help_text
    assert "{timestamp}" in help_text
    assert "生产迁移已有库时不要使用" in help_text


async def test_async_main_refuses_apply_when_database_is_missing(
    tmp_path: Path,
    capsys,
) -> None:
    apply_migrations = load_apply_migrations_module()
    db_path = tmp_path / "missing" / "bot.db"

    exit_code = await apply_migrations.async_main(
        ["--db-path", str(db_path), "--apply"]
    )

    assert exit_code == 1
    assert db_path.exists() is False
    output = capsys.readouterr().out
    assert "refused_missing_database=True" in output
    assert "--allow-create" in output


async def test_async_main_refuses_apply_when_database_is_unreadable(
    tmp_path: Path,
    capsys,
) -> None:
    apply_migrations = load_apply_migrations_module()
    db_path = tmp_path / "bot.db"
    db_path.write_text("not a sqlite database", encoding="utf-8")

    exit_code = await apply_migrations.async_main(
        ["--db-path", str(db_path), "--apply"]
    )

    assert exit_code == 1
    assert db_path.read_text(encoding="utf-8") == "not a sqlite database"
    output = capsys.readouterr().out
    assert "refused_unreadable_database=True" in output
    assert "not readable SQLite" in output


async def test_async_main_returns_success_when_schema_already_ready(
    tmp_path: Path,
    capsys,
) -> None:
    apply_migrations = load_apply_migrations_module()
    db_path = tmp_path / "bot.db"
    await apply_migrations.run_migration(
        str(db_path),
        should_apply=True,
        allow_create=True,
    )

    exit_code = await apply_migrations.async_main(["--db-path", str(db_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "mode=dry-run" in output
    assert "missing_after=none" in output
    assert "database schema already ready" in output
    assert "add --apply" not in output


async def test_async_main_json_output_is_machine_readable(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    apply_migrations = load_apply_migrations_module()
    db_path = tmp_path / "bot.db"
    monkeypatch.setattr(apply_migrations, "datetime", _FrozenDateTime)

    exit_code = await apply_migrations.async_main(["--db-path", str(db_path), "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["metadata"]["generated_at"] == "2026-06-11T12:10:00Z"
    assert payload["metadata"]["database_path"] == str(db_path)
    assert payload["report"]["applied"] is False
    assert payload["report"]["schema_ready"] is False
    assert "customer_profiles" in payload["report"]["missing_before"]
    assert "conversation_summaries" in payload["report"]["missing_before"]
    assert "customer_groups" in payload["report"]["missing_before"]


async def test_async_main_json_output_can_be_written_to_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    apply_migrations = load_apply_migrations_module()
    db_path = tmp_path / "bot.db"
    report_path = tmp_path / "reports" / "migration.json"
    monkeypatch.setattr(apply_migrations, "datetime", _FrozenDateTime)

    exit_code = await apply_migrations.async_main(
        ["--db-path", str(db_path), "--json", "--output", str(report_path)]
    )

    assert exit_code == 1
    assert report_path.read_bytes().startswith(apply_migrations.UTF8_BOM)
    payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    assert payload["metadata"]["generated_at"] == "2026-06-11T12:10:00Z"
    assert payload["report"]["database_path"] == str(db_path)


async def test_async_main_json_output_expands_timestamp_placeholder(
    monkeypatch,
    tmp_path: Path,
) -> None:
    apply_migrations = load_apply_migrations_module()
    db_path = tmp_path / "bot.db"
    report_template = tmp_path / "reports" / "migration-{timestamp}.json"
    expected_path = tmp_path / "reports" / "migration-20260611-121000.json"
    monkeypatch.setattr(apply_migrations, "datetime", _FrozenDateTime)

    exit_code = await apply_migrations.async_main(
        ["--db-path", str(db_path), "--json", "--output", str(report_template)]
    )

    assert exit_code == 1
    assert expected_path.exists() is True
    assert report_template.exists() is False


async def test_async_main_json_output_refuses_to_overwrite_file(
    tmp_path: Path,
    capsys,
) -> None:
    apply_migrations = load_apply_migrations_module()
    db_path = tmp_path / "bot.db"
    report_path = tmp_path / "migration.json"
    report_path.write_text("existing", encoding="utf-8")

    exit_code = await apply_migrations.async_main(
        ["--db-path", str(db_path), "--json", "--output", str(report_path)]
    )

    assert exit_code == 2
    assert report_path.read_text(encoding="utf-8") == "existing"
    assert "拒绝覆盖" in capsys.readouterr().err


async def test_async_main_output_requires_json_flag(
    tmp_path: Path,
    capsys,
) -> None:
    apply_migrations = load_apply_migrations_module()

    exit_code = await apply_migrations.async_main(
        ["--output", str(tmp_path / "migration.json")]
    )

    assert exit_code == 2
    assert "--output 必须配合 --json 使用" in capsys.readouterr().err
