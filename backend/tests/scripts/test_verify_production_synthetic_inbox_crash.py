"""生产合成 inbox 崩溃专项合同测试。"""

import sqlite3
from pathlib import Path

import pytest

from scripts import verify_production_synthetic_inbox_crash as verification


def create_inbox_schema(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE inbox_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                queue_name TEXT NOT NULL,
                message_key TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'received',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                lease_until TEXT,
                next_attempt_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def test_real_subprocess_crash_reclaims_and_cleans(tmp_path: Path) -> None:
    database_path = (tmp_path / "bot.db").resolve()
    create_inbox_schema(database_path)

    report = verification.run_verification(
        database_path,
        lease_seconds=1,
        processing_timeout_seconds=5,
        recovery_timeout_seconds=8,
    )

    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert report["boundaries"]["synthetic_residue"] is False
    with sqlite3.connect(database_path) as connection:
        assert verification.count_synthetic_records(connection) == 0


def test_target_requires_existing_absolute_database(tmp_path: Path) -> None:
    relative_path = Path("bot.db")
    with pytest.raises(ValueError, match="绝对 SQLite"):
        verification.validate_target(relative_path, 5)
    with pytest.raises(ValueError, match="绝对 SQLite"):
        verification.validate_target((tmp_path / "missing.db").resolve(), 5)


def test_target_rejects_unsafe_lease(tmp_path: Path) -> None:
    database_path = (tmp_path / "bot.db").resolve()
    database_path.write_bytes(b"sqlite")
    with pytest.raises(ValueError, match="1 到 60"):
        verification.validate_target(database_path, 0)
    with pytest.raises(ValueError, match="1 到 60"):
        verification.validate_target(database_path, 61)


def test_cli_requires_explicit_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(
        verification.sys,
        "argv",
        ["verify_production_synthetic_inbox_crash.py", "--db", "bot.db"],
    )
    with pytest.raises(SystemExit):
        verification.parse_args()
