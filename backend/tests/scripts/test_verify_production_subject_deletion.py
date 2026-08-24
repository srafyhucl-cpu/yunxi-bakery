"""生产合成主体删除专项脚本安全合同测试。"""

import sqlite3
from pathlib import Path

import pytest

from scripts import verify_production_subject_deletion as verification


def create_minimal_schema(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE sessions (id TEXT PRIMARY KEY, channel TEXT, user_id TEXT);
            CREATE TABLE messages (id TEXT PRIMARY KEY, session_id TEXT, role TEXT, content TEXT);
            CREATE TABLE customer_profiles (id TEXT PRIMARY KEY, channel TEXT, user_id TEXT, display_name TEXT);
            CREATE TABLE customer_consent_ledger (channel TEXT, user_id TEXT, status TEXT, UNIQUE(channel, user_id));
            CREATE TABLE miniapp_addresses (id TEXT PRIMARY KEY, user_id TEXT, receiver_name TEXT, receiver_phone TEXT, address TEXT);
            CREATE TABLE orders (id TEXT PRIMARY KEY, session_id TEXT, channel TEXT, user_id TEXT, products TEXT);
            CREATE TABLE customer_master (id TEXT PRIMARY KEY, tenant_id TEXT, display_name TEXT);
            CREATE TABLE customer_identity_links (id TEXT PRIMARY KEY, tenant_id TEXT, customer_id TEXT, identity_type TEXT, identity_value TEXT, source_system TEXT);
            """
        )


def test_fixture_seed_and_cleanup_leave_no_residue(tmp_path: Path) -> None:
    database_path = tmp_path / "bot.db"
    create_minimal_schema(database_path)
    subject = verification.SyntheticSubject.create()

    with verification.database_connection(database_path) as connection:
        verification.ensure_subject_absent(connection, subject)
        verification.seed_subject(connection, subject)
        assert verification.count_subject_records(connection, subject) == 7
        assert verification.consent_status(connection, subject) == "granted"
        verification.cleanup_subject(connection, subject)
        assert verification.count_all_subject_records(connection, subject) == 0
        assert verification.database_integrity_ok(connection) is True


def test_target_requires_loopback_api_and_existing_database(tmp_path: Path) -> None:
    database_path = tmp_path / "bot.db"
    database_path.write_bytes(b"sqlite")

    with pytest.raises(ValueError, match="loopback"):
        verification.validate_target(database_path, "https://yunxifood.cn")
    with pytest.raises(ValueError, match="服务根地址"):
        verification.validate_target(database_path, "http://127.0.0.1:7001/health")
    with pytest.raises(FileNotFoundError):
        verification.validate_target(tmp_path / "missing.db", "http://127.0.0.1:7001")


def test_cli_requires_explicit_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(
        verification.sys,
        "argv",
        ["verify_production_subject_deletion.py", "--db", "bot.db"],
    )

    with pytest.raises(SystemExit):
        verification.parse_args()
