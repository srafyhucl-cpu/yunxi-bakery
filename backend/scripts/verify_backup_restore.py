"""验证 SQLite 备份与恢复 round-trip，不覆盖已有文件。"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def verify_backup_restore(
    database_path: Path,
    backup_path: Path,
    restore_path: Path,
) -> dict[str, object]:
    """创建备份、恢复副本并检查三个数据库的完整性。"""
    for output_path in (backup_path, restore_path):
        if output_path.exists():
            raise FileExistsError(f"拒绝覆盖已有输出文件: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database_path) as source:
        _assert_integrity(source, "source")
        with sqlite3.connect(backup_path) as backup:
            source.backup(backup)
            _assert_integrity(backup, "backup")

    with sqlite3.connect(backup_path) as backup:
        with sqlite3.connect(restore_path) as restored:
            backup.backup(restored)
            _assert_integrity(restored, "restore")

    return {
        "status": "ok",
        "database": str(database_path),
        "backup": str(backup_path),
        "restore": str(restore_path),
    }


def _assert_integrity(connection: sqlite3.Connection, label: str) -> None:
    row = connection.execute("PRAGMA integrity_check").fetchone()
    if not row or row[0] != "ok":
        raise RuntimeError(f"{label} SQLite integrity_check 失败")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="验证 SQLite backup/restore round-trip"
    )
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--restore", required=True, type=Path)
    args = parser.parse_args()
    report = verify_backup_restore(args.db, args.backup, args.restore)
    sys.stdout.write(json.dumps(report, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
