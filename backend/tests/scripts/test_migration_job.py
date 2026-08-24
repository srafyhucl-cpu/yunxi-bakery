"""SQLite 迁移 job 的恢复边界测试。"""

import sqlite3
from pathlib import Path

import pytest

from scripts import migration_job


def _create_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker (value) VALUES (?)", ("before",))


@pytest.mark.asyncio
async def test_dry_run_does_not_create_or_mutate_database(tmp_path: Path) -> None:
    database_path = tmp_path / "missing" / "bot.db"

    report = await migration_job.run_job(database_path, mode="dry-run")

    assert report.schema_ready is False
    assert database_path.exists() is False


@pytest.mark.asyncio
async def test_apply_creates_backup_and_makes_schema_ready(tmp_path: Path) -> None:
    database_path = tmp_path / "bot.db"
    backup_path = tmp_path / "backup.db"
    _create_database(database_path)

    report = await migration_job.run_job(
        database_path,
        mode="apply",
        backup_path=backup_path,
        require_off_disk=False,
    )

    assert report.schema_ready is True
    assert report.rolled_back is False
    assert backup_path.exists() is True
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("before",)


@pytest.mark.asyncio
async def test_rollback_restores_backup_state(tmp_path: Path) -> None:
    database_path = tmp_path / "bot.db"
    backup_path = tmp_path / "backup.db"
    _create_database(database_path)
    migration_job._create_backup(database_path, backup_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE marker SET value = ?", ("changed",))

    report = await migration_job.run_job(
        database_path,
        mode="rollback",
        backup_path=backup_path,
        require_off_disk=False,
    )

    assert report.rolled_back is True
    assert report.schema_ready is False
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("before",)


@pytest.mark.asyncio
async def test_apply_refuses_existing_backup(tmp_path: Path) -> None:
    database_path = tmp_path / "bot.db"
    backup_path = tmp_path / "backup.db"
    _create_database(database_path)
    backup_path.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        await migration_job.run_job(
            database_path,
            mode="apply",
            backup_path=backup_path,
            require_off_disk=False,
        )


@pytest.mark.asyncio
async def test_apply_failure_restores_backup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "bot.db"
    backup_path = tmp_path / "backup.db"
    _create_database(database_path)

    async def fail_migration(*args, **kwargs):
        with sqlite3.connect(database_path) as connection:
            connection.execute("UPDATE marker SET value = ?", ("partial",))
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr(migration_job, "run_migration", fail_migration)
    report = await migration_job.run_job(
        database_path,
        mode="apply",
        backup_path=backup_path,
        require_off_disk=False,
    )

    assert report.schema_ready is False
    assert report.rolled_back is True
    assert "injected migration failure" in report.error
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("before",)


@pytest.mark.asyncio
async def test_apply_rejects_same_device_backup_by_default(tmp_path: Path) -> None:
    database_path = tmp_path / "bot.db"
    backup_path = tmp_path / "backup.db"
    _create_database(database_path)

    with pytest.raises(ValueError, match="同一设备"):
        await migration_job.run_job(
            database_path,
            mode="apply",
            backup_path=backup_path,
        )
