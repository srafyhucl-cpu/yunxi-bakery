"""创建并验证 SQLite 的 AES-GCM 加密备份。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sqlite3
import struct
import tempfile
from contextlib import closing
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENVELOPE_MAGIC = b"YXBK"
ENVELOPE_VERSION = 1
NONCE_SIZE = 12
KEY_SIZE = 32


def create_encrypted_backup(
    database_path: Path, encrypted_path: Path, key_path: Path
) -> dict[str, object]:
    """创建不可覆盖的加密备份，并验证解密后的 SQLite 完整性。"""
    if not database_path.is_file():
        raise FileNotFoundError(f"源数据库不存在: {database_path}")
    _refuse_existing(encrypted_path)
    encrypted_path.parent.mkdir(parents=True, exist_ok=True)
    key = _read_key(key_path)
    plaintext = _sqlite_backup_bytes(database_path, encrypted_path.parent)
    nonce = os.urandom(NONCE_SIZE)
    digest = hashlib.sha256(plaintext).hexdigest()
    header = {
        "algorithm": "AES-256-GCM",
        "plaintext_sha256": digest,
        "version": ENVELOPE_VERSION,
        "nonce": base64.b64encode(nonce).decode("ascii"),
    }
    header_bytes = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, header_bytes)
    envelope = (
        ENVELOPE_MAGIC
        + struct.pack(">I", len(header_bytes))
        + header_bytes
        + ciphertext
    )
    encrypted_path.write_bytes(envelope)
    try:
        verify_encrypted_backup(encrypted_path, key_path)
    except Exception:
        encrypted_path.unlink()
        raise
    return {
        "status": "ok",
        "backup": str(encrypted_path),
        "plaintext_sha256": digest,
        "algorithm": header["algorithm"],
    }


def verify_encrypted_backup(encrypted_path: Path, key_path: Path) -> dict[str, object]:
    """解密到临时 SQLite 文件并执行完整性检查，不生成恢复副本。"""
    key = _read_key(key_path)
    header, ciphertext = _read_envelope(encrypted_path)
    nonce = base64.b64decode(header["nonce"], validate=True)
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, _header_bytes(header))
    digest = hashlib.sha256(plaintext).hexdigest()
    if digest != header["plaintext_sha256"]:
        raise ValueError("解密备份 SHA-256 校验失败")
    with tempfile.NamedTemporaryFile(
        prefix="yunxi-backup-", suffix=".db", dir=encrypted_path.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
        temporary.write(plaintext)
    try:
        with closing(sqlite3.connect(temporary_path)) as connection:
            _assert_integrity(connection)
    finally:
        temporary_path.unlink()
    return {"status": "ok", "plaintext_sha256": digest}


def _sqlite_backup_bytes(database_path: Path, directory: Path) -> bytes:
    with tempfile.NamedTemporaryFile(
        prefix="yunxi-backup-source-", suffix=".db", dir=directory, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with (
            closing(sqlite3.connect(database_path)) as source,
            closing(sqlite3.connect(temporary_path)) as backup,
        ):
            _assert_integrity(source)
            source.backup(backup)
            _assert_integrity(backup)
        return temporary_path.read_bytes()
    finally:
        temporary_path.unlink()


def _read_key(key_path: Path) -> bytes:
    key = key_path.read_bytes()
    if len(key) != KEY_SIZE:
        raise ValueError(f"加密备份密钥必须正好是 {KEY_SIZE} 字节")
    return key


def _read_envelope(encrypted_path: Path) -> tuple[dict[str, object], bytes]:
    payload = encrypted_path.read_bytes()
    if payload[:4] != ENVELOPE_MAGIC:
        raise ValueError("加密备份格式无效")
    header_size = struct.unpack(">I", payload[4:8])[0]
    header_start = 8
    header_end = header_start + header_size
    header = json.loads(payload[header_start:header_end])
    if header.get("version") != ENVELOPE_VERSION:
        raise ValueError("不支持的加密备份版本")
    return header, payload[header_end:]


def _header_bytes(header: dict[str, object]) -> bytes:
    return json.dumps(header, sort_keys=True, separators=(",", ":")).encode()


def _refuse_existing(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"拒绝覆盖已有输出文件: {path}")


def _assert_integrity(connection: sqlite3.Connection) -> None:
    row = connection.execute("PRAGMA integrity_check").fetchone()
    if not row or row[0] != "ok":
        raise RuntimeError("SQLite integrity_check 失败")


def main() -> int:
    parser = argparse.ArgumentParser(description="创建 SQLite AES-GCM 加密备份")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--key-file", required=True, type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            create_encrypted_backup(args.db, args.output, args.key_file),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
