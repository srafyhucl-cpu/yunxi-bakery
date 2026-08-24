from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
from types import ModuleType


def load_seed_baseline_knowledge_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "seed_baseline_knowledge.py"
    )
    spec = importlib.util.spec_from_file_location(
        "seed_baseline_knowledge", script_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_knowledge_table(db_path: Path) -> None:
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            "CREATE TABLE knowledge_base ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "category TEXT NOT NULL, "
            "content_type TEXT NOT NULL DEFAULT 'faq', "
            "title TEXT NOT NULL, "
            "content TEXT NOT NULL, "
            "keywords TEXT DEFAULT '', "
            "priority INTEGER DEFAULT 0, "
            "is_active INTEGER DEFAULT 1, "
            "last_sync_source TEXT DEFAULT 'admin_manual', "
            "last_sync_ref TEXT DEFAULT '', "
            "content_origin TEXT DEFAULT 'admin_manual', "
            "created_by TEXT DEFAULT '', "
            "updated_by TEXT DEFAULT '', "
            "vector_sync_status TEXT DEFAULT 'pending')"
        )


def _count_rows(db_path: Path) -> int:
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute("SELECT COUNT(id) FROM knowledge_base")
        return int(cursor.fetchone()[0])


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 6, 11, 12, 30, 0, tzinfo=tz)


def test_seed_baseline_knowledge_reports_missing_database(tmp_path: Path) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()
    db_path = tmp_path / "missing" / "bot.db"

    report = seed_baseline.seed_baseline_knowledge(
        str(db_path),
        should_apply=False,
    )

    assert report.schema_ready is False
    assert report.inserted_count == 0
    assert db_path.exists() is False


def test_main_reports_migration_dry_run_action_when_schema_missing(
    tmp_path: Path,
    capsys,
) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()
    db_path = tmp_path / "bot.db"
    db_path.write_text("", encoding="utf-8")

    exit_code = seed_baseline.main(["--db-path", str(db_path)])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "apply_migrations.py dry-run" in output
    assert "confirm target database path" in output
    assert "apply_migrations.py --apply" not in output


def test_main_reports_schema_not_ready_for_invalid_database_file(
    tmp_path: Path,
    capsys,
) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()
    db_path = tmp_path / "bot.db"
    db_path.write_text("not a sqlite database", encoding="utf-8")

    exit_code = seed_baseline.main(["--db-path", str(db_path)])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "schema_ready=False" in output
    assert "apply_migrations.py dry-run" in output


def test_main_refuses_apply_when_database_is_invalid(
    tmp_path: Path,
    capsys,
) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()
    db_path = tmp_path / "bot.db"
    original_content = "not a sqlite database"
    db_path.write_text(original_content, encoding="utf-8")

    exit_code = seed_baseline.main(["--db-path", str(db_path), "--apply"])

    assert exit_code == 1
    assert db_path.read_text(encoding="utf-8") == original_content
    output = capsys.readouterr().out
    assert "mode=apply" in output
    assert "schema_ready=False" in output
    assert "apply_migrations.py dry-run" in output
    assert "then rerun migrations with --apply" in output
    assert "seed_baseline_knowledge.py --apply" not in output
    assert "rebuild_embeddings.py --apply" not in output


def test_seed_baseline_knowledge_dry_run_does_not_write_rows(
    tmp_path: Path,
) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()
    db_path = tmp_path / "bot.db"
    _create_knowledge_table(db_path)

    report = seed_baseline.seed_baseline_knowledge(
        str(db_path),
        should_apply=False,
    )

    assert report.schema_ready is True
    assert report.applied is False
    assert report.inserted_count == 0
    assert report.total_entries == len(seed_baseline.BASELINE_ENTRIES)
    assert _count_rows(db_path) == 0


def test_seed_baseline_knowledge_apply_inserts_active_pending_rows(
    tmp_path: Path,
) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()
    db_path = tmp_path / "bot.db"
    _create_knowledge_table(db_path)

    report = seed_baseline.seed_baseline_knowledge(
        str(db_path),
        should_apply=True,
    )

    assert report.applied is True
    assert report.inserted_count == len(seed_baseline.BASELINE_ENTRIES)
    assert report.active_rows_after == len(seed_baseline.BASELINE_ENTRIES)
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT category, vector_sync_status, last_sync_source "
            "FROM knowledge_base ORDER BY id"
        ).fetchall()
    assert {row[0] for row in rows} >= {"faq", "policy", "after_sales", "store_info"}
    assert {row[1] for row in rows} == {"pending"}
    assert {row[2] for row in rows} == {seed_baseline.BASELINE_SOURCE}


def test_seed_baseline_knowledge_apply_is_idempotent(tmp_path: Path) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()
    db_path = tmp_path / "bot.db"
    _create_knowledge_table(db_path)

    first_report = seed_baseline.seed_baseline_knowledge(
        str(db_path),
        should_apply=True,
    )
    second_report = seed_baseline.seed_baseline_knowledge(
        str(db_path),
        should_apply=True,
    )

    assert first_report.inserted_count == len(seed_baseline.BASELINE_ENTRIES)
    assert second_report.inserted_count == 0
    assert second_report.skipped_count == len(seed_baseline.BASELINE_ENTRIES)
    assert _count_rows(db_path) == len(seed_baseline.BASELINE_ENTRIES)


def test_main_reports_dry_run_action(tmp_path: Path, capsys) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()
    db_path = tmp_path / "bot.db"
    _create_knowledge_table(db_path)

    exit_code = seed_baseline.main(["--db-path", str(db_path)])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "mode=dry-run" in output
    assert "confirm target database path" in output
    assert "then rerun with --apply" in output


def test_main_reports_existing_baseline_as_success(tmp_path: Path, capsys) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()
    db_path = tmp_path / "bot.db"
    _create_knowledge_table(db_path)
    seed_baseline.seed_baseline_knowledge(str(db_path), should_apply=True)

    exit_code = seed_baseline.main(["--db-path", str(db_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "mode=dry-run" in output
    assert "baseline knowledge already exists" in output
    assert "add --apply" not in output


def test_main_reports_embedding_rebuild_dry_run_after_apply(
    tmp_path: Path,
    capsys,
) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()
    db_path = tmp_path / "bot.db"
    _create_knowledge_table(db_path)

    exit_code = seed_baseline.main(["--db-path", str(db_path), "--apply"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "mode=apply" in output
    assert "rebuild_embeddings.py dry-run" in output
    assert "rebuild_embeddings.py --apply" not in output


def test_main_json_output_is_machine_readable(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()
    db_path = tmp_path / "bot.db"
    _create_knowledge_table(db_path)
    monkeypatch.setattr(seed_baseline, "datetime", _FrozenDateTime)

    exit_code = seed_baseline.main(["--db-path", str(db_path), "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["metadata"]["generated_at"] == "2026-06-11T12:30:00Z"
    assert payload["metadata"]["database_path"] == str(db_path)
    assert payload["metadata"]["baseline_source"] == seed_baseline.BASELINE_SOURCE
    assert payload["report"]["applied"] is False
    assert payload["report"]["schema_ready"] is True
    assert payload["report"]["total_entries"] == len(seed_baseline.BASELINE_ENTRIES)


def test_main_json_output_can_be_written_to_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()
    db_path = tmp_path / "bot.db"
    report_path = tmp_path / "reports" / "baseline-seed.json"
    _create_knowledge_table(db_path)
    monkeypatch.setattr(seed_baseline, "datetime", _FrozenDateTime)

    exit_code = seed_baseline.main(
        ["--db-path", str(db_path), "--json", "--output", str(report_path)]
    )

    assert exit_code == 1
    assert report_path.read_bytes().startswith(seed_baseline.UTF8_BOM)
    payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    assert payload["metadata"]["generated_at"] == "2026-06-11T12:30:00Z"
    assert payload["report"]["database_path"] == str(db_path)


def test_main_json_output_expands_timestamp_placeholder(
    monkeypatch,
    tmp_path: Path,
) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()
    db_path = tmp_path / "bot.db"
    report_template = tmp_path / "reports" / "baseline-seed-{timestamp}.json"
    expected_path = tmp_path / "reports" / "baseline-seed-20260611-123000.json"
    _create_knowledge_table(db_path)
    monkeypatch.setattr(seed_baseline, "datetime", _FrozenDateTime)

    exit_code = seed_baseline.main(
        ["--db-path", str(db_path), "--json", "--output", str(report_template)]
    )

    assert exit_code == 1
    assert expected_path.exists() is True
    assert report_template.exists() is False


def test_main_json_output_refuses_to_overwrite_file(
    tmp_path: Path,
    capsys,
) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()
    db_path = tmp_path / "bot.db"
    report_path = tmp_path / "baseline-seed.json"
    _create_knowledge_table(db_path)
    report_path.write_text("existing", encoding="utf-8")

    exit_code = seed_baseline.main(
        ["--db-path", str(db_path), "--json", "--output", str(report_path)]
    )

    assert exit_code == 2
    assert report_path.read_text(encoding="utf-8") == "existing"
    assert "拒绝覆盖" in capsys.readouterr().err


def test_main_output_requires_json_flag(
    tmp_path: Path,
    capsys,
) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()

    exit_code = seed_baseline.main(["--output", str(tmp_path / "baseline-seed.json")])

    assert exit_code == 2
    assert "--output 必须配合 --json 使用" in capsys.readouterr().err


def test_parse_args_help_mentions_json_output(capsys) -> None:
    seed_baseline = load_seed_baseline_knowledge_module()

    try:
        seed_baseline.parse_args(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    help_text = capsys.readouterr().out
    assert "--json" in help_text
    assert "--output" in help_text
    assert "{timestamp}" in help_text
