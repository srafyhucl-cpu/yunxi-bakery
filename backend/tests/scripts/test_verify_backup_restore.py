"""SQLite 备份恢复 round-trip 合同测试。"""

import sqlite3

import pytest

from scripts.verify_backup_restore import verify_backup_restore


def test_verify_backup_restore_round_trip(tmp_path) -> None:
    database_path = tmp_path / "source.db"
    backup_path = tmp_path / "backup.db"
    restore_path = tmp_path / "restore.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE facts (value TEXT NOT NULL)")
        connection.execute("INSERT INTO facts (value) VALUES (?)", ("synthetic",))

    report = verify_backup_restore(database_path, backup_path, restore_path)

    assert report["status"] == "ok"
    with sqlite3.connect(restore_path) as connection:
        assert (
            connection.execute("SELECT value FROM facts").fetchone()[0] == "synthetic"
        )


def test_verify_backup_restore_refuses_existing_output(tmp_path) -> None:
    database_path = tmp_path / "source.db"
    backup_path = tmp_path / "backup.db"
    restore_path = tmp_path / "restore.db"
    sqlite3.connect(database_path).close()
    backup_path.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        verify_backup_restore(database_path, backup_path, restore_path)
