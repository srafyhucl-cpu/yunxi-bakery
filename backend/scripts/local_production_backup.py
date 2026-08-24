"""从生产拉取一致快照并在本地创建加密长期备份。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts.encrypted_backup import create_encrypted_backup  # noqa: E402

DEFAULT_HOST = "47.94.102.250"
DEFAULT_USER = "root"
DEFAULT_PORT = 22
DEFAULT_REMOTE_DB = "/opt/apps/yunxibakebot/data/bot.db"
DEFAULT_REMOTE_TEMP_DIR = "/dev/shm"
DEFAULT_RETENTION_DAYS = 30
DEFAULT_MINIMUM_BACKUPS = 3
BACKUP_PATTERN = "bot_backup_*.ybak"
SAFE_REMOTE_PATH = re.compile(r"^/[A-Za-z0-9._/-]+$")


def run_backup(
    *,
    backup_dir: Path,
    key_file: Path,
    ssh_key: Path,
    host: str = DEFAULT_HOST,
    user: str = DEFAULT_USER,
    port: int = DEFAULT_PORT,
    remote_db: str = DEFAULT_REMOTE_DB,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    minimum_backups: int = DEFAULT_MINIMUM_BACKUPS,
    now: datetime | None = None,
) -> dict[str, object]:
    """执行一次远端快照、本地加密、验证和单文件保留清理。"""
    _validate_inputs(backup_dir, key_file, ssh_key, retention_days, minimum_backups)
    current_time = now or datetime.now(timezone.utc)
    run_id = uuid.uuid4().hex
    remote_snapshot = f"{DEFAULT_REMOTE_TEMP_DIR}/yunxi-backup-{run_id}.db"
    local_snapshot = backup_dir / f".yunxi-backup-{run_id}.db"
    output = backup_dir / f"bot_backup_{current_time:%Y%m%d_%H%M%S}.ybak"
    remote_created = False
    try:
        _validate_remote_path(remote_db)
        remote_created = True
        _run_ssh(
            ssh_key,
            host,
            user,
            port,
            _snapshot_command(remote_db, remote_snapshot),
        )
        _run_scp(ssh_key, host, user, port, remote_snapshot, local_snapshot)
        encrypted = create_encrypted_backup(local_snapshot, output, key_file)
        removed = prune_one_expired_backup(
            backup_dir,
            retention_days=retention_days,
            minimum_backups=minimum_backups,
            now=current_time,
            exclude=output,
        )
        return {
            "status": "ok",
            "backup": encrypted["backup"],
            "algorithm": encrypted["algorithm"],
            "retention_removed": str(removed) if removed else "",
        }
    finally:
        if local_snapshot.exists():
            local_snapshot.unlink()
        if remote_created:
            _run_ssh(
                ssh_key,
                host,
                user,
                port,
                f"rm -f -- '{remote_snapshot}'",
                check=False,
            )


def prune_one_expired_backup(
    backup_dir: Path,
    *,
    retention_days: int,
    minimum_backups: int,
    now: datetime,
    exclude: Path | None = None,
) -> Path | None:
    """每次最多删除一个过期备份，并始终保留最低份数。"""
    resolved_dir = backup_dir.resolve()
    candidates = sorted(
        (
            path
            for path in resolved_dir.glob(BACKUP_PATTERN)
            if path.is_file()
            and (exclude is None or path.resolve() != exclude.resolve())
        ),
        key=lambda path: path.stat().st_mtime,
    )
    if len(candidates) + (1 if exclude and exclude.exists() else 0) <= minimum_backups:
        return None
    cutoff = now - timedelta(days=retention_days)
    oldest = candidates[0] if candidates else None
    if oldest is None:
        return None
    modified = datetime.fromtimestamp(oldest.stat().st_mtime, timezone.utc)
    if modified >= cutoff or oldest.resolve().parent != resolved_dir:
        return None
    oldest.unlink()
    return oldest


def _validate_inputs(
    backup_dir: Path,
    key_file: Path,
    ssh_key: Path,
    retention_days: int,
    minimum_backups: int,
) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    if backup_dir.drive.upper() == "C:":
        raise ValueError("备份目录不得位于 C 盘")
    if not key_file.is_file() or key_file.stat().st_size != 32:
        raise ValueError("备份密钥必须是存在的 32 字节文件")
    if not ssh_key.is_file():
        raise FileNotFoundError("SSH 密钥不存在")
    if retention_days < 1 or minimum_backups < 1:
        raise ValueError("保留天数和最低份数必须大于零")


def _snapshot_command(remote_db: str, remote_snapshot: str) -> str:
    return (
        f"test -f '{remote_db}' && "
        f"sqlite3 '{remote_db}' \".backup '{remote_snapshot}'\" && "
        f"test \"$(sqlite3 '{remote_snapshot}' 'PRAGMA integrity_check;')\" = ok"
    )


def _validate_remote_path(remote_db: str) -> None:
    if not SAFE_REMOTE_PATH.fullmatch(remote_db):
        raise ValueError("远端数据库路径包含不允许的字符")


def _run_ssh(
    ssh_key: Path,
    host: str,
    user: str,
    port: int,
    remote_command: str,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "ssh.exe",
            "-i",
            str(ssh_key),
            "-p",
            str(port),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            f"{user}@{host}",
            remote_command,
        ],
        check=check,
        capture_output=True,
        text=True,
    )


def _run_scp(
    ssh_key: Path,
    host: str,
    user: str,
    port: int,
    remote_snapshot: str,
    local_snapshot: Path,
) -> None:
    subprocess.run(
        [
            "scp.exe",
            "-i",
            str(ssh_key),
            "-P",
            str(port),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            f"{user}@{host}:{remote_snapshot}",
            str(local_snapshot),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="创建本地生产 SQLite 加密备份")
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--key-file", required=True, type=Path)
    parser.add_argument("--ssh-key", required=True, type=Path)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--remote-db", default=DEFAULT_REMOTE_DB)
    parser.add_argument("--retention-days", default=DEFAULT_RETENTION_DAYS, type=int)
    parser.add_argument("--minimum-backups", default=DEFAULT_MINIMUM_BACKUPS, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_backup(
        backup_dir=args.backup_dir,
        key_file=args.key_file,
        ssh_key=args.ssh_key,
        host=args.host,
        user=args.user,
        port=args.port,
        remote_db=args.remote_db,
        retention_days=args.retention_days,
        minimum_backups=args.minimum_backups,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
