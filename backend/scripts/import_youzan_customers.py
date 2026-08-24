"""有赞客户正式迁移入口脚本。"""

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
from scripts.audit_youzan_customer_migration import (  # noqa: E402
    DEFAULT_CUSTOMER_CSV,
    DEFAULT_ORDERS_CSV,
    default_source_batch_id,
    run_audit,
    run_import,
    write_json_report,
)
from scripts.preflight_production import (  # noqa: E402
    get_missing_database_tables,
    is_readable_sqlite_database,
    resolve_project_path,
)

OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
UTF8_BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class YouzanCustomerImportReport:
    """正式迁移脚本的执行报告。"""

    database_path: str
    customer_csv: str
    orders_csv: str
    tenant_id: str
    source_batch_id: str
    applied: bool
    allow_create: bool
    refused_missing_database: bool
    refused_unreadable_database: bool
    schema_ready_before: bool
    schema_ready_after: bool
    issues_count: int
    planned_total_records: int
    planned_bucket_summary: dict[str, int]
    applied_total_records: int
    applied_bucket_summary: dict[str, int]
    actions_summary: dict[str, int]

    @property
    def apply_ready(self) -> bool:
        if self.refused_unreadable_database:
            return False
        if self.database_path == ":memory:":
            return True
        if Path(self.database_path).exists():
            return True
        return self.allow_create

    def to_dict(self) -> dict[str, object]:
        return {
            "database_path": self.database_path,
            "customer_csv": self.customer_csv,
            "orders_csv": self.orders_csv,
            "tenant_id": self.tenant_id,
            "source_batch_id": self.source_batch_id,
            "applied": self.applied,
            "allow_create": self.allow_create,
            "apply_ready": self.apply_ready,
            "refused_missing_database": self.refused_missing_database,
            "refused_unreadable_database": self.refused_unreadable_database,
            "schema_ready_before": self.schema_ready_before,
            "schema_ready_after": self.schema_ready_after,
            "issues_count": self.issues_count,
            "planned_total_records": self.planned_total_records,
            "planned_bucket_summary": self.planned_bucket_summary,
            "applied_total_records": self.applied_total_records,
            "applied_bucket_summary": self.applied_bucket_summary,
            "actions_summary": self.actions_summary,
        }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Youzan customers")
    parser.add_argument(
        "--customer-csv",
        default=str(DEFAULT_CUSTOMER_CSV),
        help="有赞客户导出 CSV 路径。",
    )
    parser.add_argument(
        "--orders-csv",
        default=str(DEFAULT_ORDERS_CSV),
        help="有赞订单导出 CSV 路径。",
    )
    parser.add_argument(
        "--db-path",
        default=settings.DB_PATH,
        help="目标 SQLite 数据库路径，默认读取 DB_PATH。",
    )
    parser.add_argument(
        "--tenant-id",
        default="yunxi",
        help="customer 主档租户 ID，默认 yunxi。",
    )
    parser.add_argument(
        "--source-batch-id",
        default="",
        help="来源批次 ID；不传则自动按时间生成。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际执行 customer 导入；不加该参数时只做 dry-run。",
    )
    parser.add_argument(
        "--allow-create",
        action="store_true",
        help="允许运行 --apply 时创建不存在的数据库文件；生产导入已有库时不要使用。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出机器可读 JSON。",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="配合 --json 使用，将报告写入指定文件，支持 {timestamp}。",
    )
    return parser.parse_args(argv)


def expand_output_path(output_path_value: str) -> Path:
    timestamp = datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)
    expanded_value = output_path_value.replace(OUTPUT_TIMESTAMP_PLACEHOLDER, timestamp)
    return Path(expanded_value)


def ensure_output_path_available(output_path_value: str) -> Path:
    output_path = expand_output_path(output_path_value)
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")
    return output_path


def _is_in_memory_database(db_path_value: str) -> bool:
    return db_path_value == ":memory:"


def _resolve_database_path_value(db_path_value: str) -> str:
    if _is_in_memory_database(db_path_value):
        return ":memory:"
    return str(resolve_project_path(db_path_value))


def _build_planned_bucket_summary(audit_summary: dict[str, object]) -> dict[str, int]:
    return {
        "auto_merge": int(audit_summary["auto_merge_customer_count"]),
        "new_master": int(audit_summary["new_master_customer_count"]),
        "pending_review": int(audit_summary["pending_review_customer_count"]),
    }


async def run_customer_import(
    *,
    customer_csv_path: Path,
    orders_csv_path: Path,
    db_path_value: str,
    tenant_id: str,
    source_batch_id: str,
    should_apply: bool,
    allow_create: bool,
) -> YouzanCustomerImportReport:
    audit_artifacts = run_audit(customer_csv_path, orders_csv_path)
    planned_bucket_summary = _build_planned_bucket_summary(audit_artifacts.summary)
    planned_total_records = int(audit_artifacts.summary["total_customers"])
    issues_count = len(audit_artifacts.issues)
    resolved_db_path = _resolve_database_path_value(db_path_value)
    in_memory_database = _is_in_memory_database(db_path_value)

    refused_missing_database = False
    refused_unreadable_database = False
    schema_ready_before = False
    schema_ready_after = False
    applied_total_records = 0
    applied_bucket_summary: dict[str, int] = {}
    actions_summary: dict[str, int] = {}

    if in_memory_database:
        schema_ready_before = False
        schema_ready_after = should_apply
    else:
        database_path = Path(resolved_db_path)
        if database_path.exists():
            refused_unreadable_database = not is_readable_sqlite_database(database_path)
            if not refused_unreadable_database:
                schema_ready_before = not get_missing_database_tables(database_path)
        else:
            refused_missing_database = not allow_create

    can_apply = not refused_unreadable_database and (
        in_memory_database or Path(resolved_db_path).exists() or allow_create
    )

    if should_apply and can_apply:
        import_artifacts = await run_import(
            db_path_value=resolved_db_path,
            tenant_id=tenant_id,
            source_batch_id=source_batch_id,
            customer_csv_path=customer_csv_path,
            orders_csv_path=orders_csv_path,
        )
        applied_total_records = import_artifacts.total_records
        applied_bucket_summary = import_artifacts.bucket_summary
        actions_summary = import_artifacts.actions_summary
        if in_memory_database:
            schema_ready_after = True
        else:
            schema_ready_after = not get_missing_database_tables(Path(resolved_db_path))

    return YouzanCustomerImportReport(
        database_path=resolved_db_path,
        customer_csv=str(customer_csv_path),
        orders_csv=str(orders_csv_path),
        tenant_id=tenant_id,
        source_batch_id=source_batch_id,
        applied=should_apply,
        allow_create=allow_create,
        refused_missing_database=refused_missing_database,
        refused_unreadable_database=refused_unreadable_database,
        schema_ready_before=schema_ready_before,
        schema_ready_after=schema_ready_after,
        issues_count=issues_count,
        planned_total_records=planned_total_records,
        planned_bucket_summary=planned_bucket_summary,
        applied_total_records=applied_total_records,
        applied_bucket_summary=applied_bucket_summary,
        actions_summary=actions_summary,
    )


def print_report(report: YouzanCustomerImportReport) -> None:
    mode = "apply" if report.applied else "dry-run"
    print("Youzan customer formal import")
    print(f"mode={mode}")
    print(f"db_path={report.database_path}")
    print(f"tenant_id={report.tenant_id}")
    print(f"source_batch_id={report.source_batch_id}")
    print(f"allow_create={report.allow_create}")
    print(f"apply_ready={report.apply_ready}")
    print(f"refused_missing_database={report.refused_missing_database}")
    print(f"refused_unreadable_database={report.refused_unreadable_database}")
    print(f"schema_ready_before={report.schema_ready_before}")
    print(f"schema_ready_after={report.schema_ready_after}")
    print(f"planned_total_records={report.planned_total_records}")
    print(
        "planned_bucket_summary="
        + json.dumps(report.planned_bucket_summary, ensure_ascii=False)
    )
    print(f"issues_count={report.issues_count}")
    print(f"applied_total_records={report.applied_total_records}")
    print(
        "applied_bucket_summary="
        + json.dumps(report.applied_bucket_summary, ensure_ascii=False)
    )
    print("actions_summary=" + json.dumps(report.actions_summary, ensure_ascii=False))
    if report.refused_missing_database:
        print(
            "action=database file is missing; verify --db-path, or add --allow-create before rerunning --apply"
        )
    elif report.refused_unreadable_database:
        print(
            "action=database file is not readable SQLite; verify --db-path or restore database before importing"
        )
    elif report.applied:
        print("action=customer import applied")
    elif report.schema_ready_before:
        print("action=review dry-run output, then rerun with --apply")
    else:
        print(
            "action=review dry-run output; target database schema will be auto-created or migrated during --apply"
        )


def build_json_report(report: YouzanCustomerImportReport) -> dict[str, object]:
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "status": "ready" if report.apply_ready else "failed",
        "metadata": {
            "generated_at": generated_at,
            "project_root": str(ROOT_DIR),
            "database_path": report.database_path,
            "customer_csv": report.customer_csv,
            "orders_csv": report.orders_csv,
            "tenant_id": report.tenant_id,
            "source_batch_id": report.source_batch_id,
        },
        "report": report.to_dict(),
    }


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

    source_batch_id = args.source_batch_id or default_source_batch_id()
    customer_csv_path = resolve_project_path(args.customer_csv)
    orders_csv_path = resolve_project_path(args.orders_csv)
    try:
        report = await run_customer_import(
            customer_csv_path=customer_csv_path,
            orders_csv_path=orders_csv_path,
            db_path_value=args.db_path,
            tenant_id=args.tenant_id,
            source_batch_id=source_batch_id,
            should_apply=args.apply,
            allow_create=args.allow_create,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        json_bytes = (
            json.dumps(build_json_report(report), ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        if output_path is None:
            sys.stdout.buffer.write(json_bytes)
        else:
            write_json_report(output_path, json_bytes)
    else:
        print_report(report)
    return 0 if report.apply_ready else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
