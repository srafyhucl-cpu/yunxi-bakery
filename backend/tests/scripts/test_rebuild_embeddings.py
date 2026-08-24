from __future__ import annotations

import importlib.util
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from types import ModuleType

import numpy as np

KNOWLEDGE_GOVERNANCE_COLUMNS_SQL = (
    "audience TEXT DEFAULT 'all', "
    "review_status TEXT DEFAULT 'published', "
    "valid_from TEXT DEFAULT '', "
    "valid_until TEXT DEFAULT '', "
    "reviewed_by TEXT DEFAULT '', "
    "reviewed_at TEXT DEFAULT ''"
)


def load_rebuild_embeddings_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "rebuild_embeddings.py"
    )
    spec = importlib.util.spec_from_file_location("rebuild_embeddings", script_path)
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
            "youzan_item_id TEXT DEFAULT '', "
            "title TEXT NOT NULL, "
            "content TEXT NOT NULL, "
            "is_active INTEGER DEFAULT 1, " + KNOWLEDGE_GOVERNANCE_COLUMNS_SQL + ")"
        )
        conn.execute(
            "INSERT INTO knowledge_base (title, content, is_active) VALUES (?, ?, ?)",
            ("配送规则", "同城配送提前一天预约", 1),
        )


def _create_legacy_knowledge_table(db_path: Path) -> None:
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            "CREATE TABLE knowledge_base ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "youzan_item_id TEXT DEFAULT '', "
            "title TEXT NOT NULL, "
            "content TEXT NOT NULL, "
            "is_active INTEGER DEFAULT 1)"
        )
        conn.execute(
            "INSERT INTO knowledge_base (title, content, is_active) VALUES (?, ?, ?)",
            ("配送规则", "同城配送提前一天预约", 1),
        )


def _write_embedding_cache(index_path: Path) -> None:
    np.save(index_path.with_suffix(".npy"), np.array([], dtype=np.float32))
    index_path.with_suffix(".json").write_text(
        '{"doc_keys": [], "ready": true, "data_hash": "test"}',
        encoding="utf-8",
    )


async def test_rebuild_embeddings_dry_run_does_not_write_files(tmp_path: Path) -> None:
    rebuild_embeddings = load_rebuild_embeddings_module()
    db_path = tmp_path / "bot.db"
    index_path = tmp_path / "embeddings"
    _create_knowledge_table(db_path)

    report = await rebuild_embeddings.rebuild_embeddings(
        str(db_path),
        str(index_path),
        should_apply=False,
    )

    assert report.applied is False
    assert report.active_docs == 1
    assert report.files_ready_before is False
    assert report.files_ready_after is False
    assert index_path.with_suffix(".npy").exists() is False
    assert index_path.with_suffix(".json").exists() is False


async def test_rebuild_embeddings_apply_writes_cache_pair(tmp_path: Path) -> None:
    rebuild_embeddings = load_rebuild_embeddings_module()
    db_path = tmp_path / "bot.db"
    index_path = tmp_path / "cache" / "embeddings"
    _create_knowledge_table(db_path)

    report = await rebuild_embeddings.rebuild_embeddings(
        str(db_path),
        str(index_path),
        should_apply=True,
    )

    assert report.applied is True
    assert report.active_docs == 1
    assert report.files_ready_after is True
    assert index_path.with_suffix(".npy").exists() is True
    assert index_path.with_suffix(".json").exists() is True


async def test_rebuild_embeddings_apply_requires_active_docs(tmp_path: Path) -> None:
    rebuild_embeddings = load_rebuild_embeddings_module()
    db_path = tmp_path / "bot.db"
    index_path = tmp_path / "embeddings"

    report = await rebuild_embeddings.rebuild_embeddings(
        str(db_path),
        str(index_path),
        should_apply=True,
    )

    assert report.active_docs == 0
    assert report.files_ready_after is False


async def test_rebuild_embeddings_requires_knowledge_schema(tmp_path: Path) -> None:
    rebuild_embeddings = load_rebuild_embeddings_module()
    db_path = tmp_path / "bot.db"
    index_path = tmp_path / "embeddings"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY)")

    report = await rebuild_embeddings.rebuild_embeddings(
        str(db_path),
        str(index_path),
        should_apply=True,
    )

    assert report.schema_ready is False
    assert report.active_docs == 0
    assert report.files_ready_after is False
    assert index_path.with_suffix(".npy").exists() is False
    assert index_path.with_suffix(".json").exists() is False


async def test_rebuild_embeddings_requires_governance_columns(
    tmp_path: Path,
) -> None:
    rebuild_embeddings = load_rebuild_embeddings_module()
    db_path = tmp_path / "bot.db"
    index_path = tmp_path / "embeddings"
    _create_legacy_knowledge_table(db_path)

    report = await rebuild_embeddings.rebuild_embeddings(
        str(db_path),
        str(index_path),
        should_apply=True,
    )

    assert report.schema_ready is False
    assert report.active_docs == 0
    assert report.files_ready_after is False
    assert index_path.with_suffix(".npy").exists() is False
    assert index_path.with_suffix(".json").exists() is False


async def test_async_main_refuses_apply_when_database_is_invalid(
    tmp_path: Path,
    capsys,
) -> None:
    rebuild_embeddings = load_rebuild_embeddings_module()
    db_path = tmp_path / "bot.db"
    index_path = tmp_path / "embeddings"
    original_content = "not a sqlite database"
    db_path.write_text(original_content, encoding="utf-8")

    exit_code = await rebuild_embeddings.async_main(
        ["--db-path", str(db_path), "--index-path", str(index_path), "--apply"]
    )

    assert exit_code == 1
    assert db_path.read_text(encoding="utf-8") == original_content
    assert index_path.with_suffix(".npy").exists() is False
    assert index_path.with_suffix(".json").exists() is False
    output = capsys.readouterr().out
    assert "mode=apply" in output
    assert "schema_ready=False" in output
    assert "apply_migrations.py dry-run" in output
    assert "then rerun migrations with --apply" in output


async def test_async_main_reports_dry_run_action(tmp_path: Path, capsys) -> None:
    rebuild_embeddings = load_rebuild_embeddings_module()
    db_path = tmp_path / "bot.db"
    index_path = tmp_path / "embeddings"
    _create_knowledge_table(db_path)

    exit_code = await rebuild_embeddings.async_main(
        ["--db-path", str(db_path), "--index-path", str(index_path)]
    )

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "mode=dry-run" in output
    assert "active_docs=1" in output
    assert "confirm database and index paths" in output
    assert "then rerun with --apply" in output


async def test_async_main_reports_migration_action_when_schema_missing(
    tmp_path: Path,
    capsys,
) -> None:
    rebuild_embeddings = load_rebuild_embeddings_module()
    db_path = tmp_path / "bot.db"
    index_path = tmp_path / "embeddings"
    db_path.write_text("", encoding="utf-8")

    exit_code = await rebuild_embeddings.async_main(
        ["--db-path", str(db_path), "--index-path", str(index_path)]
    )

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "schema_ready=False" in output
    assert "preflight_production.py" in output
    assert "apply_migrations.py dry-run" in output
    assert "confirm target database path" in output
    assert "apply_migrations.py --apply" not in output


async def test_async_main_reports_ready_cache_without_apply_action(
    tmp_path: Path,
    capsys,
) -> None:
    rebuild_embeddings = load_rebuild_embeddings_module()
    db_path = tmp_path / "bot.db"
    index_path = tmp_path / "embeddings"
    _create_knowledge_table(db_path)
    _write_embedding_cache(index_path)

    exit_code = await rebuild_embeddings.async_main(
        ["--db-path", str(db_path), "--index-path", str(index_path)]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "mode=dry-run" in output
    assert "files_ready_after=True" in output
    assert "embedding cache already ready" in output
    assert "add --apply" not in output
