"""运行生产同构、数据隔离的主体删除与消息崩溃整改 Harness。"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import logging
import secrets
import sqlite3
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import httpx
from fastapi import FastAPI

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.api.channels.storefront.privacy import (  # noqa: E402
    create_storefront_privacy_router,
)
from app.config import settings  # noqa: E402
from app.database import close_db, init_db  # noqa: E402
from app.repository.customer_profile_repo import CustomerProfileRepo  # noqa: E402
from app.repository.base import DatabaseHandle  # noqa: E402
from app.repository.inbox_repo import InboxRepo  # noqa: E402
from app.repository.privacy_repo import PrivacyRepo  # noqa: E402
from app.service.channels.storefront.auth import StorefrontAuthService  # noqa: E402
from app.service.customer_consent import CustomerConsentService  # noqa: E402
from app.service.privacy_lifecycle import PrivacyLifecycleService  # noqa: E402

SYNTHETIC_USER_ID = "remediation-harness-subject"
SYNTHETIC_QUEUE = "remediation_harness"
SYNTHETIC_MESSAGE_KEY = "remediation-harness:message"
WORKER_LEASE_SECONDS = 1
LEASE_RECOVERY_WAIT_SECONDS = 2.0
PROCESSING_WAIT_SECONDS = 5.0
PROCESSING_POLL_SECONDS = 0.05
PROCESS_TERMINATION_TIMEOUT_SECONDS = 5
WORKER_HOLD_SECONDS = 300
CLEANUP_TIMEOUT_SECONDS = 3.0
CLEANUP_RETRY_SECONDS = 0.1
HARNESS_BASE_URL = "http://isolated-harness"
SUBJECT_EXPORT_PATH = "/api/v1/miniapp/privacy/subject/export"
SUBJECT_DELETE_PATH = "/api/v1/miniapp/privacy/subject"


@dataclass(frozen=True)
class HarnessCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


async def run_harness(work_dir: Path) -> dict[str, object]:
    """执行两条隔离风险链并返回无敏感数据报告。"""
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    database_path = work_dir / f"remediation-harness-{uuid.uuid4().hex}.db"
    checks: list[HarnessCheck] = []
    worker: subprocess.Popen[bytes] | None = None
    original_secret = settings.STOREFRONT_AUTH_SECRET
    original_legacy = settings.STOREFRONT_AUTH_ALLOW_LEGACY_HEADER
    settings.STOREFRONT_AUTH_SECRET = secrets.token_urlsafe(32)
    settings.STOREFRONT_AUTH_ALLOW_LEGACY_HEADER = False
    connection: aiosqlite.Connection | None = await init_db(str(database_path))
    try:
        checks.extend(await _run_privacy_scenario(connection))
        await InboxRepo(DatabaseHandle(connection)).enqueue(
            SYNTHETIC_QUEUE,
            SYNTHETIC_MESSAGE_KEY,
            json.dumps({"kind": "synthetic"}),
        )
        # B3.5（问题 8）：InboxRepo 不再自提交——独立写流程须显式提交，
        # 否则 close 时回滚导致 worker 子进程读不到该消息。
        await connection.commit()
        await close_db(connection)
        connection = None

        worker = _start_claim_worker(database_path)
        claimed_before_crash = await asyncio.to_thread(
            _wait_for_processing,
            database_path,
        )
        checks.append(
            HarnessCheck(
                "queue.claimed_before_crash",
                claimed_before_crash,
                "" if claimed_before_crash else "message did not enter processing",
            )
        )
        worker.kill()
        worker.wait(timeout=PROCESS_TERMINATION_TIMEOUT_SECONDS)
        worker = None
        await asyncio.sleep(LEASE_RECOVERY_WAIT_SECONDS)

        connection = await init_db(str(database_path))
        checks.extend(await _verify_queue_recovery(connection))
    finally:
        if worker is not None and worker.poll() is None:
            worker.kill()
            worker.wait(timeout=PROCESS_TERMINATION_TIMEOUT_SECONDS)
        if connection is not None:
            await close_db(connection)
            connection = None
        settings.STOREFRONT_AUTH_SECRET = original_secret
        settings.STOREFRONT_AUTH_ALLOW_LEGACY_HEADER = original_legacy
        gc.collect()
        _remove_database_files(database_path)

    return build_report(checks)


async def _run_privacy_scenario(
    connection: aiosqlite.Connection,
) -> list[HarnessCheck]:
    await _seed_synthetic_subject(connection)
    database = DatabaseHandle(connection)
    app = FastAPI()
    app.include_router(
        create_storefront_privacy_router(
            CustomerConsentService(CustomerProfileRepo(database)),
            PrivacyLifecycleService(PrivacyRepo(database)),
        )
    )
    token = StorefrontAuthService().issue_access_token(SYNTHETIC_USER_ID)
    headers = {"authorization": f"Bearer {token}"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=HARNESS_BASE_URL,
    ) as client:
        exported = await client.get(
            SUBJECT_EXPORT_PATH,
            headers=headers,
        )
        deleted = await client.delete(
            SUBJECT_DELETE_PATH,
            headers=headers,
        )

    export_records = exported.json().get("data", {}).get("records", {})
    remaining = await _subject_record_count(connection)
    consent_rows = await connection.execute_fetchall(
        "SELECT status FROM customer_consent_ledger WHERE user_id = ?",
        (SYNTHETIC_USER_ID,),
    )
    consent_status = str(consent_rows[0]["status"]) if consent_rows else ""
    return [
        HarnessCheck(
            "privacy.authenticated_export",
            exported.status_code == 200
            and len(export_records.get("messages", [])) == 1,
            "" if exported.status_code == 200 else f"status={exported.status_code}",
        ),
        HarnessCheck(
            "privacy.authenticated_delete",
            deleted.status_code == 200 and deleted.json().get("status") == "revoked",
            "" if deleted.status_code == 200 else f"status={deleted.status_code}",
        ),
        HarnessCheck(
            "privacy.linked_records_removed",
            remaining == 0,
            "" if remaining == 0 else f"remaining={remaining}",
        ),
        HarnessCheck(
            "privacy.consent_revoked",
            consent_status == "revoked",
            "" if consent_status == "revoked" else f"status={consent_status}",
        ),
    ]


async def _seed_synthetic_subject(connection: aiosqlite.Connection) -> None:
    await connection.execute(
        "INSERT INTO sessions (id, channel, user_id) VALUES (?, ?, ?)",
        ("harness-session", "miniapp", SYNTHETIC_USER_ID),
    )
    await connection.execute(
        "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, ?, ?)",
        ("harness-message", "harness-session", "user", "synthetic-message"),
    )
    await connection.execute(
        "INSERT INTO customer_profiles (id, channel, user_id, display_name) "
        "VALUES (?, ?, ?, ?)",
        ("harness-profile", "miniapp", SYNTHETIC_USER_ID, "Synthetic Subject"),
    )
    await connection.execute(
        "INSERT INTO customer_consent_ledger (channel, user_id, status) "
        "VALUES (?, ?, ?)",
        ("miniapp", SYNTHETIC_USER_ID, "granted"),
    )
    await connection.execute(
        "INSERT INTO miniapp_addresses "
        "(id, user_id, receiver_name, receiver_phone, address) VALUES (?, ?, ?, ?, ?)",
        (
            "harness-address",
            SYNTHETIC_USER_ID,
            "Synthetic Subject",
            "synthetic-phone",
            "synthetic-address",
        ),
    )
    await connection.execute(
        "INSERT INTO orders (id, session_id, channel, user_id, products) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "harness-order",
            "harness-session",
            "miniapp",
            SYNTHETIC_USER_ID,
            "[]",
        ),
    )
    await connection.commit()


async def _subject_record_count(connection: aiosqlite.Connection) -> int:
    queries = (
        ("SELECT COUNT(*) FROM sessions WHERE user_id = ?", SYNTHETIC_USER_ID),
        ("SELECT COUNT(*) FROM customer_profiles WHERE user_id = ?", SYNTHETIC_USER_ID),
        ("SELECT COUNT(*) FROM miniapp_addresses WHERE user_id = ?", SYNTHETIC_USER_ID),
        ("SELECT COUNT(*) FROM orders WHERE user_id = ?", SYNTHETIC_USER_ID),
    )
    total = 0
    for sql, value in queries:
        rows = await connection.execute_fetchall(sql, (value,))
        total += int(rows[0][0])
    return total


def _start_claim_worker(database_path: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker-stage",
            "--db",
            str(database_path),
        ],
        cwd=ROOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_for_processing(database_path: Path) -> bool:
    deadline = time.monotonic() + PROCESSING_WAIT_SECONDS
    while time.monotonic() < deadline:
        with sqlite3.connect(database_path) as connection:
            row = connection.execute(
                "SELECT status FROM inbox_events WHERE message_key = ?",
                (SYNTHETIC_MESSAGE_KEY,),
            ).fetchone()
        if row and row[0] == "processing":
            return True
        time.sleep(PROCESSING_POLL_SECONDS)
    return False


async def _verify_queue_recovery(
    connection: aiosqlite.Connection,
) -> list[HarnessCheck]:
    repo = InboxRepo(DatabaseHandle(connection))
    reclaimed = await repo.claim(SYNTHETIC_QUEUE)
    reclaimed_key = str(reclaimed["message_key"]) if reclaimed else ""
    attempt_count = int(reclaimed["attempt_count"]) if reclaimed else 0
    if reclaimed:
        await repo.mark_processed(reclaimed_key)
    duplicate_inserted = await repo.enqueue(
        SYNTHETIC_QUEUE,
        SYNTHETIC_MESSAGE_KEY,
        json.dumps({"kind": "duplicate"}),
    )
    rows = await connection.execute_fetchall(
        "SELECT status, COUNT(*) AS count FROM inbox_events WHERE message_key = ? "
        "GROUP BY status",
        (SYNTHETIC_MESSAGE_KEY,),
    )
    final_status = str(rows[0]["status"]) if rows else ""
    final_count = int(rows[0]["count"]) if rows else 0
    pending = await repo.count_pending(SYNTHETIC_QUEUE)
    # B3.5（问题 8）：InboxRepo 不再自提交——恢复校验的写（processed / 重复键）
    # 须显式提交，保证校验基于真实持久化结果而非未提交会话。
    await connection.commit()
    return [
        HarnessCheck(
            "queue.reclaimed_after_crash",
            reclaimed_key == SYNTHETIC_MESSAGE_KEY,
            "" if reclaimed_key == SYNTHETIC_MESSAGE_KEY else "message not reclaimed",
        ),
        HarnessCheck(
            "queue.attempt_count_incremented",
            attempt_count == 2,
            "" if attempt_count == 2 else f"attempt_count={attempt_count}",
        ),
        HarnessCheck(
            "queue.single_processed_terminal",
            final_status == "processed"
            and final_count == 1
            and pending == 0
            and not duplicate_inserted,
            ""
            if final_status == "processed"
            and final_count == 1
            and pending == 0
            and not duplicate_inserted
            else "terminal idempotency mismatch",
        ),
    ]


def build_report(checks: list[HarnessCheck]) -> dict[str, object]:
    failed = [check for check in checks if not check.passed]
    return {
        "status": "passed" if not failed else "failed",
        "metadata": {
            "generated_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "isolated": True,
            "production_data_access": False,
            "legacy_auth": False,
            "external_calls": False,
        },
        "total": len(checks),
        "failed": len(failed),
        "checks": [check.to_dict() for check in checks],
        "failed_names": [check.name for check in failed],
    }


async def _worker_stage(database_path: Path) -> int:
    connection = await init_db(str(database_path))
    try:
        claimed = await InboxRepo(DatabaseHandle(connection)).claim(
            SYNTHETIC_QUEUE,
            lease_seconds=WORKER_LEASE_SECONDS,
        )
        if claimed is None:
            return 2
        await asyncio.sleep(WORKER_HOLD_SECONDS)
        return 0
    finally:
        await close_db(connection)


def _remove_database_files(database_path: Path) -> None:
    for path in (
        database_path,
        Path(str(database_path) + "-wal"),
        Path(str(database_path) + "-shm"),
    ):
        _unlink_with_retry(path)


def _unlink_with_retry(path: Path) -> None:
    deadline = time.monotonic() + CLEANUP_TIMEOUT_SECONDS
    while path.exists():
        try:
            path.unlink()
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(CLEANUP_RETRY_SECONDS)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行隔离本地整改 Harness")
    parser.add_argument("--work-dir", type=Path, help="显式 D 盘工作目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--worker-stage", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--db", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker_stage and args.db is None:
        parser.error("worker stage requires --db")
    if not args.worker_stage and args.work_dir is None:
        parser.error("必须显式提供 --work-dir")
    return args


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.worker_stage:
        return await _worker_stage(args.db)
    app_logger = logging.getLogger("yunxi_bot")
    original_log_level = app_logger.level
    handler_streams: list[tuple[logging.StreamHandler, object]] = []
    if args.json:
        app_logger.setLevel(logging.WARNING)
        for handler in app_logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler_streams.append((handler, handler.stream))
                handler.setStream(sys.stderr)
    try:
        report = await run_harness(args.work_dir)
    finally:
        app_logger.setLevel(original_log_level)
        for handler, stream in handler_streams:
            handler.setStream(stream)
    if args.json:
        sys.stdout.write(json.dumps(report, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(
            "isolated_remediation_harness "
            f"status={report['status']} total={report['total']} "
            f"failed={report['failed']}\n"
        )
    return 0 if report["status"] == "passed" else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
