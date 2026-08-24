"""在生产环境用合成主体验证真实隐私导出和删除 API。"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.service.channels.storefront.auth import StorefrontAuthService  # noqa: E402

CONFIRMATION_FLAG = "--confirm-production-synthetic-subject"
SUBJECT_PREFIX = "remediation-prod-subject-"
EXPORT_PATH = "/api/v1/miniapp/privacy/subject/export"
DELETE_PATH = "/api/v1/miniapp/privacy/subject"
EXPECTED_EXPORT_SECTIONS = (
    "messages",
    "customer_profiles",
    "consent",
    "customer_master",
    "customer_identity_links",
    "addresses",
    "orders",
)


@dataclass(frozen=True)
class SyntheticSubject:
    user_id: str
    session_id: str
    message_id: str
    profile_id: str
    address_id: str
    order_id: str
    customer_id: str
    identity_id: str

    @classmethod
    def create(cls) -> "SyntheticSubject":
        suffix = uuid.uuid4().hex
        user_id = SUBJECT_PREFIX + suffix
        return cls(
            user_id=user_id,
            session_id=f"{user_id}-session",
            message_id=f"{user_id}-message",
            profile_id=f"{user_id}-profile",
            address_id=f"{user_id}-address",
            order_id=f"{user_id}-order",
            customer_id=f"{user_id}-customer",
            identity_id=f"{user_id}-identity",
        )


def run_verification(
    database_path: Path,
    base_url: str,
    *,
    timeout_seconds: float = 15.0,
) -> dict[str, object]:
    """执行一次生产真实 API 专项并返回无敏感数据报告。"""
    database_path = database_path.resolve()
    validate_target(database_path, base_url)
    subject = SyntheticSubject.create()
    checks: dict[str, bool] = {}
    try:
        with database_connection(database_path) as connection:
            checks["database.integrity_before"] = database_integrity_ok(connection)
            ensure_subject_absent(connection, subject)
            seed_subject(connection, subject)
            checks["fixture.seeded"] = count_subject_records(connection, subject) == 7

        token = StorefrontAuthService().issue_access_token(subject.user_id)
        with httpx.Client(base_url=base_url, timeout=timeout_seconds) as client:
            exported = client.get(
                EXPORT_PATH,
                headers={"authorization": f"Bearer {token}"},
            )
            deleted = client.delete(
                DELETE_PATH,
                headers={"authorization": f"Bearer {token}"},
            )
        export_records = exported.json().get("data", {}).get("records", {})
        checks["api.authenticated_export"] = exported.status_code == 200 and all(
            len(export_records.get(section, [])) == 1
            for section in EXPECTED_EXPORT_SECTIONS
        )
        checks["api.authenticated_delete"] = (
            deleted.status_code == 200 and deleted.json().get("status") == "revoked"
        )

        with database_connection(database_path) as connection:
            checks["database.linked_records_removed"] = (
                count_subject_records(connection, subject) == 0
            )
            checks["database.consent_revoked"] = (
                consent_status(connection, subject) == "revoked"
            )
            checks["database.integrity_after"] = database_integrity_ok(connection)
    finally:
        with database_connection(database_path) as connection:
            cleanup_subject(connection, subject)
            checks["database.synthetic_residue_removed"] = (
                count_all_subject_records(connection, subject) == 0
            )

    failed_names = [name for name, passed in checks.items() if not passed]
    return {
        "status": "passed" if not failed_names else "failed",
        "total": len(checks),
        "failed": len(failed_names),
        "failed_names": failed_names,
        "checks": checks,
        "boundaries": {
            "synthetic_subject": True,
            "real_customer_data_read": False,
            "real_customer_data_deleted": False,
            "token_exposed": False,
            "export_payload_exposed": False,
            "synthetic_residue": not checks.get(
                "database.synthetic_residue_removed", False
            ),
        },
    }


def validate_target(database_path: Path, base_url: str) -> None:
    if not database_path.is_file():
        raise FileNotFoundError("生产 SQLite 文件不存在")
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("生产主体删除专项只允许 loopback HTTP API")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("base URL 必须是无 path/query/fragment 的服务根地址")


@contextmanager
def database_connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path, timeout=15)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
    finally:
        connection.close()


def ensure_subject_absent(
    connection: sqlite3.Connection,
    subject: SyntheticSubject,
) -> None:
    if count_all_subject_records(connection, subject):
        raise RuntimeError("合成主体 ID 碰撞，拒绝继续")


def seed_subject(connection: sqlite3.Connection, subject: SyntheticSubject) -> None:
    with connection:
        connection.execute(
            "INSERT INTO sessions (id, channel, user_id) VALUES (?, ?, ?)",
            (subject.session_id, "miniapp", subject.user_id),
        )
        connection.execute(
            "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, ?, ?)",
            (
                subject.message_id,
                subject.session_id,
                "user",
                "synthetic-subject-message",
            ),
        )
        connection.execute(
            "INSERT INTO customer_profiles (id, channel, user_id, display_name) VALUES (?, ?, ?, ?)",
            (subject.profile_id, "miniapp", subject.user_id, "Synthetic Subject"),
        )
        connection.execute(
            "INSERT INTO customer_consent_ledger (channel, user_id, status) VALUES (?, ?, ?)",
            ("miniapp", subject.user_id, "granted"),
        )
        connection.execute(
            "INSERT INTO miniapp_addresses (id, user_id, receiver_name, receiver_phone, address) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                subject.address_id,
                subject.user_id,
                "Synthetic",
                "synthetic",
                "synthetic",
            ),
        )
        connection.execute(
            "INSERT INTO orders (id, session_id, channel, user_id, products) VALUES (?, ?, ?, ?, ?)",
            (subject.order_id, subject.session_id, "miniapp", subject.user_id, "[]"),
        )
        connection.execute(
            "INSERT INTO customer_master (id, tenant_id, display_name) VALUES (?, ?, ?)",
            (subject.customer_id, "default", "Synthetic Subject"),
        )
        connection.execute(
            "INSERT INTO customer_identity_links "
            "(id, tenant_id, customer_id, identity_type, identity_value, source_system) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                subject.identity_id,
                "default",
                subject.customer_id,
                "miniapp_openid",
                subject.user_id,
                "miniapp",
            ),
        )


def count_subject_records(
    connection: sqlite3.Connection,
    subject: SyntheticSubject,
) -> int:
    queries = (
        ("SELECT COUNT(*) FROM sessions WHERE id = ?", subject.session_id),
        ("SELECT COUNT(*) FROM messages WHERE id = ?", subject.message_id),
        ("SELECT COUNT(*) FROM customer_profiles WHERE id = ?", subject.profile_id),
        ("SELECT COUNT(*) FROM miniapp_addresses WHERE id = ?", subject.address_id),
        ("SELECT COUNT(*) FROM orders WHERE id = ?", subject.order_id),
        ("SELECT COUNT(*) FROM customer_master WHERE id = ?", subject.customer_id),
        (
            "SELECT COUNT(*) FROM customer_identity_links WHERE id = ?",
            subject.identity_id,
        ),
    )
    return sum(
        int(connection.execute(sql, (value,)).fetchone()[0]) for sql, value in queries
    )


def count_all_subject_records(
    connection: sqlite3.Connection,
    subject: SyntheticSubject,
) -> int:
    consent_count = connection.execute(
        "SELECT COUNT(*) FROM customer_consent_ledger WHERE user_id = ?",
        (subject.user_id,),
    ).fetchone()[0]
    return count_subject_records(connection, subject) + int(consent_count)


def consent_status(connection: sqlite3.Connection, subject: SyntheticSubject) -> str:
    row = connection.execute(
        "SELECT status FROM customer_consent_ledger WHERE user_id = ?",
        (subject.user_id,),
    ).fetchone()
    return str(row[0]) if row else ""


def cleanup_subject(connection: sqlite3.Connection, subject: SyntheticSubject) -> None:
    with connection:
        for sql, value in (
            ("DELETE FROM messages WHERE id = ?", subject.message_id),
            ("DELETE FROM customer_profiles WHERE id = ?", subject.profile_id),
            ("DELETE FROM miniapp_addresses WHERE id = ?", subject.address_id),
            ("DELETE FROM orders WHERE id = ?", subject.order_id),
            ("DELETE FROM customer_identity_links WHERE id = ?", subject.identity_id),
            ("DELETE FROM customer_master WHERE id = ?", subject.customer_id),
            ("DELETE FROM sessions WHERE id = ?", subject.session_id),
            (
                "DELETE FROM customer_consent_ledger WHERE user_id = ?",
                subject.user_id,
            ),
        ):
            connection.execute(sql, (value,))


def database_integrity_ok(connection: sqlite3.Connection) -> bool:
    row = connection.execute("PRAGMA integrity_check").fetchone()
    return bool(row and row[0] == "ok")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证生产合成主体隐私删除闭环")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:7001")
    parser.add_argument(CONFIRMATION_FLAG, action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.confirm_production_synthetic_subject:
        parser.error(f"必须显式提供 {CONFIRMATION_FLAG}")
    return args


def main() -> int:
    args = parse_args()
    report = run_verification(args.db, args.base_url)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "production_subject_deletion "
            f"status={report['status']} total={report['total']} failed={report['failed']}"
        )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
