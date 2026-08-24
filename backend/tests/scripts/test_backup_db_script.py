"""生产备份脚本安全合同测试。"""

from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "backup_db.sh"


def test_backup_script_requires_off_disk_encrypted_backup() -> None:
    content = SCRIPT.read_text(encoding="utf-8")

    assert "YUNXI_BACKUP_DIR:-/mnt/backup/yunxibakebot" in content
    assert "YUNXI_BACKUP_KEY_FILE:-/etc/yunxibakebot/backup.key" in content
    assert "DB_DEVICE" in content
    assert "BACKUP_DEVICE" in content
    assert "同一设备" in content
    assert "encrypted_backup.py" in content
    assert 'KEY_SIZE" -ne 32' in content
    assert 'KEY_MODE" != "600"' in content
    assert "rm -" not in content
