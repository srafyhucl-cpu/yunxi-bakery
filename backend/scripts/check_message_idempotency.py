"""检查消息唯一键迁移前的历史重复数据。"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def find_duplicate_message_keys(db_path: Path) -> list[dict[str, object]]:
    """返回非空渠道消息键的重复组，供迁移前人工处置。"""
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT channel_msg_id, COUNT(*) AS row_count "
            "FROM messages WHERE channel_msg_id <> '' "
            "GROUP BY channel_msg_id HAVING COUNT(*) > 1 "
            "ORDER BY channel_msg_id"
        ).fetchall()
    return [dict(row) for row in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查消息幂等键历史重复数据")
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.db_path.exists():
        print(f"数据库不存在: {args.db_path}", file=sys.stderr)
        return 2
    duplicates = find_duplicate_message_keys(args.db_path)
    report = {
        "database_path": str(args.db_path),
        "duplicate_group_count": len(duplicates),
        "duplicates": duplicates,
        "ready_for_unique_index": not duplicates,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(f"duplicate_group_count={len(duplicates)}")
        print(f"ready_for_unique_index={not duplicates}")
        for duplicate in duplicates:
            print(
                f"channel_msg_id={duplicate['channel_msg_id']} "
                f"row_count={duplicate['row_count']}"
            )
    return 0 if not duplicates else 1


if __name__ == "__main__":
    raise SystemExit(main())
