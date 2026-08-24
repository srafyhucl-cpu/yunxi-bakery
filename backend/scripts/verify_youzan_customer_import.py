"""有赞客户正式迁移结果核对脚本。"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # noqa: E402
from scripts.preflight_production import (  # noqa: E402
    is_readable_sqlite_database,
    resolve_project_path,
)

OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
UTF8_BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class CustomerImportVerificationReport:
    """正式迁移结果核对报告。"""

    database_path: str
    tenant_id: str
    source_batch_id: str
    import_report_path: str = ""
    database_exists: bool = False
    database_readable: bool = False
    batch_found: bool = False
    snapshot_count: int = 0
    distinct_customer_count: int = 0
    source_identity_count: int = 0
    linked_phone_identity_count: int = 0
    merge_review_count: int = 0
    bucket_summary: dict[str, int] | None = None
    compared_report_mode: str = ""
    expected_total_records: int = 0
    expected_bucket_summary: dict[str, int] | None = None
    expected_actions_summary: dict[str, int] | None = None
    mismatches: list[str] | None = None
    unverifiable_checks: list[str] | None = None

    @property
    def verified(self) -> bool:
        return (
            self.database_exists
            and self.database_readable
            and self.batch_found
            and not (self.mismatches or [])
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "database_path": self.database_path,
            "tenant_id": self.tenant_id,
            "source_batch_id": self.source_batch_id,
            "import_report_path": self.import_report_path,
            "database_exists": self.database_exists,
            "database_readable": self.database_readable,
            "batch_found": self.batch_found,
            "snapshot_count": self.snapshot_count,
            "distinct_customer_count": self.distinct_customer_count,
            "source_identity_count": self.source_identity_count,
            "linked_phone_identity_count": self.linked_phone_identity_count,
            "merge_review_count": self.merge_review_count,
            "bucket_summary": self.bucket_summary or {},
            "compared_report_mode": self.compared_report_mode,
            "expected_total_records": self.expected_total_records,
            "expected_bucket_summary": self.expected_bucket_summary or {},
            "expected_actions_summary": self.expected_actions_summary or {},
            "mismatches": self.mismatches or [],
            "unverifiable_checks": self.unverifiable_checks or [],
            "verified": self.verified,
        }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Youzan customer import")
    parser.add_argument(
        "--db-path",
        default=settings.DB_PATH,
        help="目标 SQLite 数据库路径，默认读取 DB_PATH。",
    )
    parser.add_argument(
        "--tenant-id",
        default="",
        help="customer 主档租户 ID；不传时优先从 --import-report 推断。",
    )
    parser.add_argument(
        "--source-batch-id",
        default="",
        help="要核对的迁移批次 ID；不传时优先从 --import-report 推断。",
    )
    parser.add_argument(
        "--import-report",
        default="",
        help="可选：正式迁移 JSON 报告路径，用于比对 total 和 bucket summary。",
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


def write_json_report(output_path: Path, json_bytes: bytes) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(UTF8_BOM + json_bytes)


def _load_import_report(import_report_value: str) -> tuple[Path, dict[str, object]]:
    report_path = resolve_project_path(import_report_value)
    if not report_path.exists():
        raise FileNotFoundError(f"导入报告不存在: {report_path}")
    payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    return report_path, payload


def _resolve_verification_scope(
    *,
    tenant_id_value: str,
    source_batch_id_value: str,
    import_report_payload: dict[str, object] | None,
) -> tuple[str, str]:
    report_metadata = {}
    report_body = {}
    if import_report_payload is not None:
        report_metadata = dict(import_report_payload.get("metadata") or {})
        report_body = dict(import_report_payload.get("report") or {})
    tenant_id = (
        tenant_id_value
        or str(report_body.get("tenant_id") or "")
        or str(report_metadata.get("tenant_id") or "")
    )
    source_batch_id = (
        source_batch_id_value
        or str(report_body.get("source_batch_id") or "")
        or str(report_metadata.get("source_batch_id") or "")
    )
    return tenant_id, source_batch_id


def _fetch_batch_snapshots(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    source_batch_id: str,
) -> list[sqlite3.Row]:
    cursor = conn.execute(
        "SELECT id, customer_id, identity_link_id, source_record_id, normalized_json "
        "FROM customer_source_snapshots "
        "WHERE tenant_id = ? AND source_batch_id = ? "
        "ORDER BY created_at ASC",
        (tenant_id, source_batch_id),
    )
    return cursor.fetchall()


def _count_customer_identities(
    conn: sqlite3.Connection,
    *,
    customer_ids: list[str],
    identity_type: str,
) -> int:
    if not customer_ids:
        return 0
    placeholders = ", ".join("?" for _ in customer_ids)
    cursor = conn.execute(
        "SELECT COUNT(DISTINCT id) "
        "FROM customer_identity_links "
        f"WHERE customer_id IN ({placeholders}) AND identity_type = ?",
        (*customer_ids, identity_type),
    )
    row = cursor.fetchone()
    return int(row[0]) if row is not None else 0


def _count_source_identities(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    source_record_ids: list[str],
) -> int:
    if not source_record_ids:
        return 0
    placeholders = ", ".join("?" for _ in source_record_ids)
    cursor = conn.execute(
        "SELECT COUNT(DISTINCT id) "
        "FROM customer_identity_links "
        f"WHERE tenant_id = ? AND identity_type = ? AND source_record_id IN ({placeholders})",
        (tenant_id, "youzan_customer", *source_record_ids),
    )
    row = cursor.fetchone()
    return int(row[0]) if row is not None else 0


def _count_related_reviews(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    batch_snapshot_ids: set[str],
    customer_ids: set[str],
) -> int:
    cursor = conn.execute(
        "SELECT id, source_customer_id, evidence_snapshot_ids_json "
        "FROM customer_merge_reviews WHERE tenant_id = ?",
        (tenant_id,),
    )
    review_count = 0
    for row in cursor.fetchall():
        source_customer_id = str(row["source_customer_id"] or "")
        evidence_snapshot_ids = json.loads(row["evidence_snapshot_ids_json"] or "[]")
        if source_customer_id in customer_ids or batch_snapshot_ids.intersection(
            set(str(item) for item in evidence_snapshot_ids)
        ):
            review_count += 1
    return review_count


def _build_bucket_summary(snapshot_rows: list[sqlite3.Row]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in snapshot_rows:
        normalized_payload = json.loads(row["normalized_json"] or "{}")
        counter[str(normalized_payload.get("proposed_bucket") or "unknown")] += 1
    return dict(counter)


def _compare_with_import_report(
    report_payload: dict[str, object] | None,
    *,
    actual_snapshot_count: int,
    actual_bucket_summary: dict[str, int],
    tenant_id: str,
    source_batch_id: str,
) -> tuple[str, int, dict[str, int], dict[str, int], list[str], list[str]]:
    if report_payload is None:
        return "", 0, {}, {}, [], []
    metadata = dict(report_payload.get("metadata") or {})
    report_body = dict(report_payload.get("report") or {})
    mismatches: list[str] = []
    unverifiable_checks: list[str] = []

    if metadata.get("tenant_id") not in ("", None, tenant_id):
        mismatches.append("import report tenant_id 与当前核对 tenant_id 不一致")
    if metadata.get("source_batch_id") not in ("", None, source_batch_id):
        mismatches.append("import report source_batch_id 与当前核对批次不一致")

    compared_report_mode = "applied"
    expected_total_records = int(report_body.get("applied_total_records") or 0)
    expected_bucket_summary = dict(report_body.get("applied_bucket_summary") or {})
    expected_actions_summary = dict(report_body.get("actions_summary") or {})
    if not bool(report_body.get("applied")):
        compared_report_mode = "planned"
        expected_total_records = int(report_body.get("planned_total_records") or 0)
        expected_bucket_summary = dict(report_body.get("planned_bucket_summary") or {})

    if expected_total_records != actual_snapshot_count:
        mismatches.append("import report total_records 与批次快照数不一致")
    if expected_bucket_summary != actual_bucket_summary:
        mismatches.append("import report bucket_summary 与批次实际分流不一致")
    if expected_actions_summary:
        actions_total = sum(int(value) for value in expected_actions_summary.values())
        if actions_total != expected_total_records:
            mismatches.append(
                "import report actions_summary 合计与 report total_records 不一致"
            )
        else:
            unverifiable_checks.append(
                "actions_summary 只能校验总量与结构，无法仅凭数据库完全反推出单条动作分布"
            )
    return (
        compared_report_mode,
        expected_total_records,
        expected_bucket_summary,
        expected_actions_summary,
        mismatches,
        unverifiable_checks,
    )


def verify_customer_import(
    *,
    db_path_value: str,
    tenant_id: str,
    source_batch_id: str,
    import_report_path: str = "",
    import_report_payload: dict[str, object] | None = None,
) -> CustomerImportVerificationReport:
    database_path = resolve_project_path(db_path_value)
    database_exists = database_path.exists()
    database_readable = database_exists and is_readable_sqlite_database(database_path)
    if not database_readable:
        return CustomerImportVerificationReport(
            database_path=str(database_path),
            tenant_id=tenant_id,
            source_batch_id=source_batch_id,
            import_report_path=import_report_path,
            database_exists=database_exists,
            database_readable=database_readable,
            mismatches=["目标数据库不存在或不可读"],
        )

    with closing(sqlite3.connect(database_path)) as conn:
        conn.row_factory = sqlite3.Row
        snapshot_rows = _fetch_batch_snapshots(
            conn,
            tenant_id=tenant_id,
            source_batch_id=source_batch_id,
        )
        bucket_summary = _build_bucket_summary(snapshot_rows)
        customer_ids = sorted(
            {
                str(row["customer_id"])
                for row in snapshot_rows
                if str(row["customer_id"] or "")
            }
        )
        source_record_ids = sorted(
            {
                str(row["source_record_id"])
                for row in snapshot_rows
                if str(row["source_record_id"] or "")
            }
        )
        snapshot_ids = {str(row["id"]) for row in snapshot_rows if str(row["id"] or "")}
        source_identity_count = _count_source_identities(
            conn,
            tenant_id=tenant_id,
            source_record_ids=source_record_ids,
        )
        linked_phone_identity_count = _count_customer_identities(
            conn,
            customer_ids=customer_ids,
            identity_type="phone",
        )
        merge_review_count = _count_related_reviews(
            conn,
            tenant_id=tenant_id,
            batch_snapshot_ids=snapshot_ids,
            customer_ids=set(customer_ids),
        )

    (
        compared_report_mode,
        expected_total_records,
        expected_bucket_summary,
        expected_actions_summary,
        mismatches,
        unverifiable_checks,
    ) = _compare_with_import_report(
        import_report_payload,
        actual_snapshot_count=len(snapshot_rows),
        actual_bucket_summary=bucket_summary,
        tenant_id=tenant_id,
        source_batch_id=source_batch_id,
    )

    if not snapshot_rows:
        mismatches.append("目标批次未找到任何 customer_source_snapshots")

    return CustomerImportVerificationReport(
        database_path=str(database_path),
        tenant_id=tenant_id,
        source_batch_id=source_batch_id,
        import_report_path=import_report_path,
        database_exists=database_exists,
        database_readable=database_readable,
        batch_found=bool(snapshot_rows),
        snapshot_count=len(snapshot_rows),
        distinct_customer_count=len(customer_ids),
        source_identity_count=source_identity_count,
        linked_phone_identity_count=linked_phone_identity_count,
        merge_review_count=merge_review_count,
        bucket_summary=bucket_summary,
        compared_report_mode=compared_report_mode,
        expected_total_records=expected_total_records,
        expected_bucket_summary=expected_bucket_summary,
        expected_actions_summary=expected_actions_summary,
        mismatches=mismatches,
        unverifiable_checks=unverifiable_checks,
    )


def print_report(report: CustomerImportVerificationReport) -> None:
    print("Youzan customer import verification")
    print(f"db_path={report.database_path}")
    print(f"tenant_id={report.tenant_id}")
    print(f"source_batch_id={report.source_batch_id}")
    print(f"database_exists={report.database_exists}")
    print(f"database_readable={report.database_readable}")
    print(f"batch_found={report.batch_found}")
    print(f"snapshot_count={report.snapshot_count}")
    print(f"distinct_customer_count={report.distinct_customer_count}")
    print(f"source_identity_count={report.source_identity_count}")
    print(f"linked_phone_identity_count={report.linked_phone_identity_count}")
    print(f"merge_review_count={report.merge_review_count}")
    print("bucket_summary=" + json.dumps(report.bucket_summary, ensure_ascii=False))
    if report.import_report_path:
        print(f"import_report_path={report.import_report_path}")
        print(f"compared_report_mode={report.compared_report_mode}")
        print(f"expected_total_records={report.expected_total_records}")
        print(
            "expected_bucket_summary="
            + json.dumps(report.expected_bucket_summary, ensure_ascii=False)
        )
        print(
            "expected_actions_summary="
            + json.dumps(report.expected_actions_summary, ensure_ascii=False)
        )
    print("verified=" + str(report.verified))
    if report.mismatches:
        print("mismatches=" + json.dumps(report.mismatches, ensure_ascii=False))
    if report.unverifiable_checks:
        print(
            "unverifiable_checks="
            + json.dumps(report.unverifiable_checks, ensure_ascii=False)
        )


def build_json_report(report: CustomerImportVerificationReport) -> dict[str, object]:
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "status": "ready" if report.verified else "failed",
        "metadata": {
            "generated_at": generated_at,
            "project_root": str(ROOT_DIR),
            "database_path": report.database_path,
            "tenant_id": report.tenant_id,
            "source_batch_id": report.source_batch_id,
            "import_report_path": report.import_report_path,
        },
        "report": report.to_dict(),
    }


def main(argv: list[str] | None = None) -> int:
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

    import_report_path = ""
    import_report_payload = None
    try:
        if args.import_report:
            resolved_path, import_report_payload = _load_import_report(
                args.import_report
            )
            import_report_path = str(resolved_path)
        tenant_id, source_batch_id = _resolve_verification_scope(
            tenant_id_value=args.tenant_id,
            source_batch_id_value=args.source_batch_id,
            import_report_payload=import_report_payload,
        )
        if not source_batch_id:
            print(
                "--source-batch-id 与 --import-report 至少提供一个。",
                file=sys.stderr,
            )
            return 2
        if not tenant_id:
            print(
                "--tenant-id 与 --import-report 中的 tenant_id 至少提供一个。",
                file=sys.stderr,
            )
            return 2
        report = verify_customer_import(
            db_path_value=args.db_path,
            tenant_id=tenant_id,
            source_batch_id=source_batch_id,
            import_report_path=import_report_path,
            import_report_payload=import_report_payload,
        )
    except (FileNotFoundError, json.JSONDecodeError) as exc:
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
    return 0 if report.verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
