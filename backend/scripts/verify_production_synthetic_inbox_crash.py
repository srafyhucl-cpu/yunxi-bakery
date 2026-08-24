"""在生产数据库中用隔离合成队列验证 worker 崩溃后的 lease 重领。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.database import close_db, init_db  # noqa: E402
from app.repository.base import DatabaseHandle  # noqa: E402
from app.repository.inbox_repo import InboxRepo  # noqa: E402

CONFIRMATION_FLAG = "--confirm-production-synthetic-inbox-crash"
QUEUE_NAME = "remediation_production_harness"
MESSAGE_PREFIX = "remediation-prod-inbox-"
DEFAULT_LEASE_SECONDS = 5
DEFAULT_PROCESSING_TIMEOUT_SECONDS = 10.0
DEFAULT_RECOVERY_TIMEOUT_SECONDS = 15.0
POLL_SECONDS = 0.1
WORKER_HOLD_SECONDS = 300


def run_verification(
    database_path: Path,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    processing_timeout_seconds: float = DEFAULT_PROCESSING_TIMEOUT_SECONDS,
    recovery_timeout_seconds: float = DEFAULT_RECOVERY_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """执行真实子进程崩溃、重领和终态校验。"""
    database_path = database_path.resolve()
    validate_target(database_path, lease_seconds)
    message_key = MESSAGE_PREFIX + uuid.uuid4().hex
    checks: dict[str, bool] = {}
    first_worker: subprocess.Popen[bytes] | None = None
    second_worker: subprocess.Popen[bytes] | None = None
    try:
        with database_connection(database_path) as connection:
            checks["database.integrity_before"] = database_integrity_ok(connection)
            ensure_no_synthetic_residue(connection)

        inserted, duplicate_inserted = asyncio.run(
            enqueue_synthetic(database_path, message_key)
        )
        checks["queue.enqueued_once"] = inserted and not duplicate_inserted
        first_worker = start_worker(database_path, message_key, lease_seconds, "hold")
        checks["queue.claimed_before_crash"] = wait_for_state(
            database_path,
            message_key,
            expected_status="processing",
            expected_attempt=1,
            timeout_seconds=processing_timeout_seconds,
        )
        first_worker.kill()
        first_worker.wait(timeout=5)
        first_worker = None

        second_worker = start_worker(
            database_path,
            message_key,
            lease_seconds,
            "complete",
            worker_wait_seconds=recovery_timeout_seconds,
        )
        checks["queue.reclaimed_after_crash"] = wait_for_state(
            database_path,
            message_key,
            expected_status="processed",
            expected_attempt=2,
            timeout_seconds=recovery_timeout_seconds,
        )
        second_worker.wait(timeout=5)
        checks["queue.recovery_worker_succeeded"] = second_worker.returncode == 0
        second_worker = None

        with database_connection(database_path) as connection:
            row = read_message_state(connection, message_key)
            checks["queue.single_processed_terminal"] = bool(
                row and row[0] == "processed" and row[1] == 2
            )
            checks["database.integrity_after"] = database_integrity_ok(connection)
    finally:
        terminate_worker(first_worker)
        terminate_worker(second_worker)
        with database_connection(database_path) as connection:
            connection.execute(
                "DELETE FROM inbox_events WHERE message_key = ?",
                (message_key,),
            )
            connection.commit()
            checks["database.synthetic_residue_removed"] = (
                count_synthetic_records(connection) == 0
            )

    failed_names = [name for name, passed in checks.items() if not passed]
    return {
        "status": "passed" if not failed_names else "failed",
        "total": len(checks),
        "failed": len(failed_names),
        "failed_names": failed_names,
        "checks": checks,
        "boundaries": {
            "synthetic_queue": True,
            "business_queue_used": False,
            "external_delivery_triggered": False,
            "payload_exposed": False,
            "synthetic_residue": not checks.get(
                "database.synthetic_residue_removed", False
            ),
        },
    }


def validate_target(database_path: Path, lease_seconds: int) -> None:
    if not database_path.is_absolute() or not database_path.is_file():
        raise ValueError("必须提供存在的绝对 SQLite 路径")
    if lease_seconds < 1 or lease_seconds > 60:
        raise ValueError("lease seconds 必须在 1 到 60 之间")


@contextmanager
def database_connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path, timeout=15)
    try:
        connection.execute("PRAGMA busy_timeout = 15000")
        yield connection
    finally:
        connection.close()


def database_integrity_ok(connection: sqlite3.Connection) -> bool:
    row = connection.execute("PRAGMA integrity_check").fetchone()
    return bool(row and row[0] == "ok")


def count_synthetic_records(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT COUNT(*) FROM inbox_events WHERE message_key LIKE ?",
        (MESSAGE_PREFIX + "%",),
    ).fetchone()
    return int(row[0]) if row else 0


def ensure_no_synthetic_residue(connection: sqlite3.Connection) -> None:
    if count_synthetic_records(connection):
        raise RuntimeError("存在未处置的生产合成 inbox 记录，拒绝继续")


async def enqueue_synthetic(database_path: Path, message_key: str) -> tuple[bool, bool]:
    connection = await init_db(str(database_path))
    try:
        repo = InboxRepo(DatabaseHandle(connection))
        inserted = await repo.enqueue(
            QUEUE_NAME,
            message_key,
            json.dumps({"kind": "synthetic-inbox-crash"}),
        )
        duplicate_inserted = await repo.enqueue(QUEUE_NAME, message_key, "{}")
        # B3.5（问题 8）：InboxRepo 不再自提交——独立写流程须显式提交，
        # 否则 close 时回滚导致子进程 worker 读不到该消息。
        await connection.commit()
        return inserted, duplicate_inserted
    finally:
        await close_db(connection)


def start_worker(
    database_path: Path,
    message_key: str,
    lease_seconds: int,
    worker_action: str,
    worker_wait_seconds: float = 0.0,
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker-stage",
            "--worker-action",
            worker_action,
            "--db",
            str(database_path),
            "--message-key",
            message_key,
            "--lease-seconds",
            str(lease_seconds),
            "--worker-wait-seconds",
            str(worker_wait_seconds),
        ],
        cwd=ROOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_state(
    database_path: Path,
    message_key: str,
    *,
    expected_status: str,
    expected_attempt: int,
    timeout_seconds: float,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with database_connection(database_path) as connection:
            row = read_message_state(connection, message_key)
        if row and row[0] == expected_status and row[1] == expected_attempt:
            return True
        time.sleep(POLL_SECONDS)
    return False


def read_message_state(
    connection: sqlite3.Connection,
    message_key: str,
) -> tuple[str, int] | None:
    row = connection.execute(
        "SELECT status, attempt_count FROM inbox_events WHERE message_key = ?",
        (message_key,),
    ).fetchone()
    return (str(row[0]), int(row[1])) if row else None


def terminate_worker(worker: subprocess.Popen[bytes] | None) -> None:
    if worker is not None and worker.poll() is None:
        worker.kill()
        worker.wait(timeout=5)


async def run_worker_stage(args: argparse.Namespace) -> int:
    connection = await init_db(str(args.db.resolve()))
    try:
        repo = InboxRepo(DatabaseHandle(connection))
        claimed = await claim_until_available(
            repo,
            lease_seconds=args.lease_seconds,
            wait_seconds=args.worker_wait_seconds,
        )
        if claimed is None or claimed["message_key"] != args.message_key:
            return 2
        if args.worker_action == "complete":
            await repo.mark_processed(args.message_key)
            # B3.5（问题 8）：InboxRepo 不再自提交——worker 终态写须显式提交
            await connection.commit()
            return 0
        await asyncio.sleep(WORKER_HOLD_SECONDS)
        return 0
    finally:
        await close_db(connection)


async def claim_until_available(
    repo: InboxRepo,
    *,
    lease_seconds: int,
    wait_seconds: float,
) -> dict[str, object] | None:
    deadline = time.monotonic() + wait_seconds
    while True:
        claimed = await repo.claim(QUEUE_NAME, lease_seconds=lease_seconds)
        if claimed is not None:
            return cast(dict[str, object], claimed)
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(POLL_SECONDS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证生产合成 inbox 崩溃恢复")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)
    parser.add_argument(CONFIRMATION_FLAG, action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--worker-stage", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--worker-action", choices=("hold", "complete"), help=argparse.SUPPRESS
    )
    parser.add_argument("--message-key", default="", help=argparse.SUPPRESS)
    parser.add_argument(
        "--worker-wait-seconds", type=float, default=0.0, help=argparse.SUPPRESS
    )
    args = parser.parse_args()
    if args.worker_stage:
        if not args.worker_action or not args.message_key:
            parser.error("worker stage 参数不完整")
    elif not args.confirm_production_synthetic_inbox_crash:
        parser.error(f"必须显式提供 {CONFIRMATION_FLAG}")
    return args


def main() -> int:
    args = parse_args()
    if args.worker_stage:
        return asyncio.run(run_worker_stage(args))
    report = run_verification(args.db, lease_seconds=args.lease_seconds)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "production_synthetic_inbox_crash "
            f"status={report['status']} total={report['total']} failed={report['failed']}"
        )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
