"""SQLite 加密备份合同测试。"""

import sqlite3

import pytest
from cryptography.exceptions import InvalidTag

from scripts.encrypted_backup import create_encrypted_backup, verify_encrypted_backup


def _create_database(path):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE facts (value TEXT NOT NULL)")
        connection.execute("INSERT INTO facts (value) VALUES (?)", ("synthetic",))


def test_encrypted_backup_round_trip_and_metadata(tmp_path) -> None:
    database_path = tmp_path / "source.db"
    encrypted_path = tmp_path / "backup.ybak"
    key_path = tmp_path / "backup.key"
    _create_database(database_path)
    key_path.write_bytes(b"1" * 32)

    report = create_encrypted_backup(database_path, encrypted_path, key_path)

    assert report["status"] == "ok"
    assert b"synthetic" not in encrypted_path.read_bytes()
    assert verify_encrypted_backup(encrypted_path, key_path)["status"] == "ok"


def test_encrypted_backup_rejects_wrong_key_and_existing_output(tmp_path) -> None:
    database_path = tmp_path / "source.db"
    encrypted_path = tmp_path / "backup.ybak"
    key_path = tmp_path / "backup.key"
    wrong_key_path = tmp_path / "wrong.key"
    _create_database(database_path)
    key_path.write_bytes(b"1" * 32)
    wrong_key_path.write_bytes(b"2" * 32)
    create_encrypted_backup(database_path, encrypted_path, key_path)

    with pytest.raises(InvalidTag):
        verify_encrypted_backup(encrypted_path, wrong_key_path)
    with pytest.raises(FileExistsError):
        create_encrypted_backup(database_path, encrypted_path, key_path)


def test_encrypted_backup_rejects_invalid_key_length(tmp_path) -> None:
    database_path = tmp_path / "source.db"
    key_path = tmp_path / "backup.key"
    _create_database(database_path)
    key_path.write_bytes(b"short")

    with pytest.raises(ValueError, match="32 字节"):
        create_encrypted_backup(database_path, tmp_path / "backup.ybak", key_path)
