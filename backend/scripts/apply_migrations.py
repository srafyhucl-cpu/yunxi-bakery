"""显式执行数据库建表与迁移。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # noqa: E402
from app.database import close_db, init_db  # noqa: E402
from scripts.preflight_production import (  # noqa: E402
    OUTPUT_TIMESTAMP_FORMAT,
    OUTPUT_TIMESTAMP_PLACEHOLDER,
    UTF8_BOM,
    get_missing_database_columns,
    get_missing_database_tables,
    is_readable_sqlite_database,
    resolve_project_path,
)


@dataclass(frozen=True)
class MigrationReport:
    database_path: Path
    applied: bool
    allow_create: bool
    refused_missing_database: bool
    refused_unreadable_database: bool
    missing_before: list[str]
    missing_after: list[str]

    @property
    def schema_ready(self) -> bool:
        return not self.missing_after

    def to_dict(self) -> dict[str, object]:
        return {
            "database_path": str(self.database_path),
            "applied": self.applied,
            "allow_create": self.allow_create,
            "refused_missing_database": self.refused_missing_database,
            "refused_unreadable_database": self.refused_unreadable_database,
            "missing_before": self.missing_before,
            "missing_after": self.missing_after,
            "schema_ready": self.schema_ready,
        }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply Platform database migrations")
    parser.add_argument(
        "--db-path",
        default=settings.DB_PATH,
        help="目标 SQLite 数据库路径，默认读取 DB_PATH。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际执行建表与迁移；不加该参数时只做 dry-run。",
    )
    parser.add_argument(
        "--allow-create",
        action="store_true",
        help="允许运行 --apply 时创建不存在的数据库文件；生产迁移已有库时不要使用。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出机器可读 JSON，便于迁移前后留档或部署脚本解析。",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "配合 --json 使用，将报告写入指定文件；目标文件已存在时会拒绝覆盖；"
            "支持 {timestamp} 自动展开为 YYYYMMDD-HHMMSS。"
        ),
    )
    return parser.parse_args(argv)


async def run_migration(
    db_path_value: str,
    *,
    should_apply: bool,
    allow_create: bool = False,
) -> MigrationReport:
    database_path = resolve_project_path(db_path_value)
    missing_before = get_missing_database_schema_items(database_path)
    missing_after = missing_before
    refused_missing_database = False
    refused_unreadable_database = (
        database_path.exists() and not is_readable_sqlite_database(database_path)
    )

    if should_apply:
        if not database_path.exists() and not allow_create:
            refused_missing_database = True
        elif refused_unreadable_database:
            missing_after = missing_before
        else:
            database_path.parent.mkdir(parents=True, exist_ok=True)
            conn = await init_db(str(database_path))
            try:
                missing_after = get_missing_database_schema_items(database_path)
            finally:
                await close_db(conn)

    return MigrationReport(
        database_path=database_path,
        applied=should_apply,
        allow_create=allow_create,
        refused_missing_database=refused_missing_database,
        refused_unreadable_database=refused_unreadable_database,
        missing_before=missing_before,
        missing_after=missing_after,
    )


def get_missing_database_schema_items(database_path: Path) -> list[str]:
    return [
        *get_missing_database_tables(database_path),
        *get_missing_database_columns(database_path),
    ]


def print_report(report: MigrationReport) -> None:
    mode = "apply" if report.applied else "dry-run"
    print("Platform database migration")
    print(f"mode={mode}")
    print(f"db_path={report.database_path}")
    print(f"allow_create={report.allow_create}")
    print(f"refused_missing_database={report.refused_missing_database}")
    print(f"refused_unreadable_database={report.refused_unreadable_database}")
    print(
        "missing_before="
        + (", ".join(report.missing_before) if report.missing_before else "none")
    )
    print(
        "missing_after="
        + (", ".join(report.missing_after) if report.missing_after else "none")
    )
    if report.refused_missing_database:
        print(
            "action=database file is missing; verify --db-path, or add --allow-create for a new database"
        )
    elif report.refused_unreadable_database:
        print(
            "action=database file is not readable SQLite; verify --db-path or restore database before applying migrations"
        )
    elif report.schema_ready and report.applied:
        print("action=database schema ready")
    elif report.schema_ready:
        print("action=database schema already ready")
    elif not report.applied:
        print(
            "action=review dry-run output, confirm target database path, then rerun with --apply"
        )
    elif report.missing_after:
        print("action=inspect migration errors before production sync")


def build_json_report(report: MigrationReport) -> dict[str, object]:
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "status": "ready" if report.schema_ready else "failed",
        "metadata": {
            "generated_at": generated_at,
            "project_root": str(ROOT_DIR),
            "database_path": str(report.database_path),
        },
        "report": report.to_dict(),
    }


def expand_output_path(output_path_value: str) -> Path:
    timestamp = datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)
    expanded_value = output_path_value.replace(OUTPUT_TIMESTAMP_PLACEHOLDER, timestamp)
    return Path(expanded_value)


def write_json_report(output_path: Path, json_bytes: bytes) -> None:
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(UTF8_BOM + json_bytes)


def ensure_output_path_available(output_path_value: str) -> Path:
    output_path = expand_output_path(output_path_value)
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")
    return output_path


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.output and not args.json:
        print("--output 必须配合 --json 使用。", file=sys.stderr)
        return 2
    if args.output:
        try:
            output_path = ensure_output_path_available(args.output)
        except FileExistsError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        output_path = None
    report = await run_migration(
        args.db_path,
        should_apply=args.apply,
        allow_create=args.allow_create,
    )
    if args.json:
        json_bytes = (
            json.dumps(build_json_report(report), ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        if output_path is None:
            sys.stdout.buffer.write(json_bytes)
        else:
            try:
                write_json_report(output_path, json_bytes)
            except FileExistsError as exc:
                print(str(exc), file=sys.stderr)
                return 2
    else:
        print_report(report)
    return 0 if report.schema_ready else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
