"""Report Youzan webhook audit events from the local SQLite database."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # noqa: E402

DEFAULT_LIMIT = 30


def main() -> None:
    args = _parse_args()
    db_path = Path(args.db_path) if args.db_path else ROOT_DIR / settings.DB_PATH
    report_date = args.date or date.today().isoformat()

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if args.business_key:
            _print_business_key(conn, args.business_key)
            return
        if args.failed:
            _print_failed(conn, report_date, args.limit)
            return
        _print_summary(conn, report_date, args.limit)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report Youzan webhook audit events.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument(
        "--db-path", help="SQLite database path. Defaults to settings.DB_PATH."
    )
    parser.add_argument(
        "--failed", action="store_true", help="Show failed/skipped events only."
    )
    parser.add_argument(
        "--business-key", help="Show events for one tid/item_id/buyer key."
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT, help="Maximum detail rows."
    )
    return parser.parse_args()


def _print_summary(conn: sqlite3.Connection, report_date: str, limit: int) -> None:
    print(f"Youzan webhook audit report: {report_date}")
    print("\nStatus summary")
    _print_rows(
        conn.execute(
            "SELECT status, COUNT(id) AS rows, MIN(received_at) AS first_at, MAX(received_at) AS last_at "
            "FROM youzan_webhook_events WHERE received_at >= ? AND received_at < date(?, '+1 day') "
            "GROUP BY status ORDER BY rows DESC",
            (f"{report_date} 00:00:00", report_date),
        )
    )

    print("\nEvent type summary")
    _print_rows(
        conn.execute(
            "SELECT event_type, business_type, COUNT(id) AS rows, "
            "SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_rows, "
            "MAX(received_at) AS last_at "
            "FROM youzan_webhook_events WHERE received_at >= ? AND received_at < date(?, '+1 day') "
            "GROUP BY event_type, business_type ORDER BY last_at DESC",
            (f"{report_date} 00:00:00", report_date),
        )
    )

    print("\nLatest events")
    _print_rows(
        conn.execute(
            "SELECT received_at, event_type, business_type, business_key, status, process_stage, "
            "error_type, duration_ms FROM youzan_webhook_events "
            "WHERE received_at >= ? AND received_at < date(?, '+1 day') "
            "ORDER BY received_at DESC LIMIT ?",
            (f"{report_date} 00:00:00", report_date, limit),
        )
    )


def _print_failed(conn: sqlite3.Connection, report_date: str, limit: int) -> None:
    print(f"Youzan webhook failed/skipped events: {report_date}")
    _print_rows(
        conn.execute(
            "SELECT received_at, msg_id, trace_id, event_type, business_type, business_key, "
            "status, process_stage, error_type, error_message FROM youzan_webhook_events "
            "WHERE received_at >= ? AND received_at < date(?, '+1 day') "
            "AND status IN ('failed', 'skipped') ORDER BY received_at DESC LIMIT ?",
            (f"{report_date} 00:00:00", report_date, limit),
        )
    )


def _print_business_key(conn: sqlite3.Connection, business_key: str) -> None:
    print(f"Youzan webhook events for business_key={business_key}")
    _print_rows(
        conn.execute(
            "SELECT received_at, msg_id, trace_id, event_type, business_type, business_key, "
            "status, process_stage, error_type, error_message, duration_ms "
            "FROM youzan_webhook_events WHERE business_key = ? ORDER BY received_at DESC",
            (business_key,),
        )
    )


def _print_rows(rows: sqlite3.Cursor) -> None:
    data = [dict(row) for row in rows.fetchall()]
    if not data:
        print("(no rows)")
        return
    headers = list(data[0].keys())
    widths = {
        header: max(len(header), *(len(str(row[header] or "")) for row in data))
        for header in headers
    }
    print("  ".join(header.ljust(widths[header]) for header in headers))
    print("  ".join("-" * widths[header] for header in headers))
    for row in data:
        print(
            "  ".join(
                str(row[header] or "").ljust(widths[header]) for header in headers
            )
        )


if __name__ == "__main__":
    main()
