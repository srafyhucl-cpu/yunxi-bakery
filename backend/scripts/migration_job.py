"""以备份和恢复边界编排 SQLite 迁移。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts.apply_migrations import (  # noqa: E402
    get_missing_database_schema_items,
    run_migration,
)


@dataclass(frozen=True)
class MigrationJobReport:
    mode: str
    database_path: Path
    backup_path: Path | None
    schema_ready: bool
    rolled_back: bool
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "database_path": str(self.database_path),
            "backup_path": str(self.backup_path) if self.backup_path else "",
            "schema_ready": self.schema_ready,
            "rolled_back": self.rolled_back,
            "error": self.error,
        }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SQLite 迁移 dry-run/apply/rollback")
    parser.add_argument("--db", required=True, type=Path, help="目标 SQLite 数据库")
    parser.add_argument(
        "--mode",
        required=True,
        choices=("dry-run", "apply", "rollback"),
        help="迁移模式",
    )
    parser.add_argument("--backup", type=Path, help="apply 前的备份或 rollback 来源")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    return parser.parse_args(argv)


async def run_job(
    database_path: Path,
    *,
    mode: str,
    backup_path: Path | None = None,
    require_off_disk: bool = True,
) -> MigrationJobReport:
    database_path = database_path.resolve()
    if mode == "dry-run":
        migration = await run_migration(str(database_path), should_apply=False)
        return MigrationJobReport(
            mode=mode,
            database_path=database_path,
            backup_path=None,
            schema_ready=migration.schema_ready,
            rolled_back=False,
        )

    if backup_path is None:
        raise ValueError("apply/rollback 必须显式提供 --backup")
    backup_path = backup_path.resolve()
    if require_off_disk:
        _assert_off_disk_backup(database_path, backup_path)

    if mode == "rollback":
        _restore_backup(backup_path, database_path)
        schema_ready = not get_missing_database_schema_items(database_path)
        return MigrationJobReport(
            mode=mode,
            database_path=database_path,
            backup_path=backup_path,
            schema_ready=schema_ready,
            rolled_back=True,
        )

    if not database_path.exists():
        raise FileNotFoundError(f"目标数据库不存在，拒绝 apply: {database_path}")
    _create_backup(database_path, backup_path)
    try:
        migration = await run_migration(str(database_path), should_apply=True)
    except Exception as exc:
        _restore_backup(backup_path, database_path)
        return MigrationJobReport(
            mode=mode,
            database_path=database_path,
            backup_path=backup_path,
            schema_ready=False,
            rolled_back=True,
            error=str(exc),
        )
    return MigrationJobReport(
        mode=mode,
        database_path=database_path,
        backup_path=backup_path,
        schema_ready=migration.schema_ready,
        rolled_back=False,
    )


def _create_backup(database_path: Path, backup_path: Path) -> None:
    if backup_path.exists():
        raise FileExistsError(f"拒绝覆盖已有备份: {backup_path}")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as source:
        _assert_integrity(source, "source")
        with sqlite3.connect(backup_path) as backup:
            source.backup(backup)
            _assert_integrity(backup, "backup")


def _assert_off_disk_backup(database_path: Path, backup_path: Path) -> None:
    """拒绝把同一设备上的备份当作生产回滚点。"""
    if not database_path.exists():
        raise FileNotFoundError(f"目标数据库不存在，拒绝检查备份设备: {database_path}")
    if not backup_path.parent.is_dir():
        raise FileNotFoundError(f"备份目录必须预先挂载: {backup_path.parent}")
    database_device = os.stat(database_path).st_dev
    backup_device = os.stat(backup_path.parent).st_dev
    if database_device == backup_device:
        raise ValueError("备份目录与数据库位于同一设备，拒绝迁移")


def _restore_backup(backup_path: Path, database_path: Path) -> None:
    if not backup_path.exists():
        raise FileNotFoundError(f"备份不存在，拒绝 rollback: {backup_path}")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup_path) as backup:
        _assert_integrity(backup, "backup")
        with sqlite3.connect(database_path) as target:
            backup.backup(target)
            _assert_integrity(target, "restored")


def _assert_integrity(connection: sqlite3.Connection, label: str) -> None:
    row = connection.execute("PRAGMA integrity_check").fetchone()
    if not row or row[0] != "ok":
        raise RuntimeError(f"{label} integrity_check 失败")


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = await run_job(
            args.db,
            mode=args.mode,
            backup_path=args.backup,
        )
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as exc:
        report = MigrationJobReport(
            mode=args.mode,
            database_path=args.db.resolve(),
            backup_path=args.backup.resolve() if args.backup else None,
            schema_ready=False,
            rolled_back=False,
            error=str(exc),
        )
    payload = {
        "status": "passed" if report.schema_ready else "failed",
        "report": report.to_dict(),
    }
    output = json.dumps(payload, ensure_ascii=False)
    print(output)
    return 0 if report.schema_ready else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
