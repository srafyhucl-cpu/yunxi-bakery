"""本地主动生产备份作业合同测试。"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import local_production_backup


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    backup_dir = tmp_path / "backups"
    key_file = tmp_path / "backup.key"
    ssh_key = tmp_path / "id_ed25519"
    key_file.write_bytes(b"k" * 32)
    ssh_key.write_text("synthetic", encoding="utf-8")
    return backup_dir, key_file, ssh_key


def test_run_backup_encrypts_and_removes_plaintext(tmp_path: Path) -> None:
    backup_dir, key_file, ssh_key = _write_inputs(tmp_path)

    def fake_scp(*args, **kwargs) -> None:
        local_path = args[-1]

        with closing(sqlite3.connect(local_path)) as connection:
            connection.execute("CREATE TABLE facts (value TEXT)")
            connection.execute("INSERT INTO facts VALUES (?)", ("synthetic",))
            connection.commit()

    with (
        patch.object(local_production_backup, "_run_ssh") as ssh,
        patch.object(local_production_backup, "_run_scp", side_effect=fake_scp),
    ):
        report = local_production_backup.run_backup(
            backup_dir=backup_dir,
            key_file=key_file,
            ssh_key=ssh_key,
            now=datetime(2026, 7, 12, tzinfo=timezone.utc),
        )

    assert report["status"] == "ok"
    assert report["algorithm"] == "AES-256-GCM"
    assert not list(backup_dir.glob("*.db"))
    assert len(list(backup_dir.glob("*.ybak"))) == 1
    assert ssh.call_count == 2


def test_run_backup_removes_plaintext_when_encryption_fails(tmp_path: Path) -> None:
    backup_dir, key_file, ssh_key = _write_inputs(tmp_path)

    def fake_scp(*args, **kwargs) -> None:
        args[-1].write_bytes(b"not-sqlite")

    with (
        patch.object(local_production_backup, "_run_ssh") as ssh,
        patch.object(local_production_backup, "_run_scp", side_effect=fake_scp),
        pytest.raises(Exception),
    ):
        local_production_backup.run_backup(
            backup_dir=backup_dir,
            key_file=key_file,
            ssh_key=ssh_key,
        )

    assert not list(backup_dir.glob("*.db"))
    assert ssh.call_count == 2


def test_run_backup_attempts_remote_cleanup_when_snapshot_fails(tmp_path: Path) -> None:
    backup_dir, key_file, ssh_key = _write_inputs(tmp_path)
    snapshot_failure = subprocess.CalledProcessError(1, ["ssh.exe"])

    with (
        patch.object(
            local_production_backup,
            "_run_ssh",
            side_effect=[snapshot_failure, subprocess.CompletedProcess([], 0)],
        ) as ssh,
        pytest.raises(subprocess.CalledProcessError),
    ):
        local_production_backup.run_backup(
            backup_dir=backup_dir,
            key_file=key_file,
            ssh_key=ssh_key,
        )

    assert ssh.call_count == 2


def test_remote_database_path_rejects_shell_characters() -> None:
    with pytest.raises(ValueError, match="不允许"):
        local_production_backup._validate_remote_path("/tmp/bot.db'; whoami")


def test_retention_removes_at_most_one_expired_backup(tmp_path: Path) -> None:
    backup_dir = tmp_path.resolve()
    now = datetime(2026, 7, 12, tzinfo=timezone.utc)
    old_time = (now - timedelta(days=40)).timestamp()
    for index in range(4):
        path = backup_dir / f"bot_backup_2026010{index}_000000.ybak"
        path.write_bytes(b"encrypted")
        os.utime(path, (old_time + index, old_time + index))

    removed = local_production_backup.prune_one_expired_backup(
        backup_dir,
        retention_days=30,
        minimum_backups=3,
        now=now,
    )

    assert removed is not None
    assert len(list(backup_dir.glob("*.ybak"))) == 3


def test_installer_uses_interactive_task_and_d_drive() -> None:
    content = (
        Path(__file__).parents[2] / "scripts" / "install_local_backup_task.ps1"
    ).read_text(encoding="utf-8")

    assert "New-ScheduledTaskTrigger -Daily" in content
    assert "-LogonType Interactive" in content
    assert "D:\\Backups\\YunxiBakeBot" in content
    assert "local_production_backup.py" in content


def test_cli_help_starts_from_script_path() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/local_production_backup.py", "--help"],
        cwd=Path(__file__).parents[2],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--backup-dir" in result.stdout
