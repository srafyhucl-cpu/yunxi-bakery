#!/bin/bash
# 生产 SQLite 加密备份脚本。
# 备份目录必须是与数据库不同设备的已挂载路径；缺失时直接失败。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DB_PATH="${YUNXI_DB_PATH:-$PROJECT_DIR/data/bot.db}"
BACKUP_DIR="${YUNXI_BACKUP_DIR:-/mnt/backup/yunxibakebot}"
KEY_PATH="${YUNXI_BACKUP_KEY_FILE:-/etc/yunxibakebot/backup.key}"
PYTHON_BIN="${YUNXI_PYTHON_BIN:-$PROJECT_DIR/venv/bin/python}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="$BACKUP_DIR/bot_backup_${TIMESTAMP}.ybak"

log_info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2
}

if [ ! -f "$DB_PATH" ]; then
    log_error "数据库文件不存在"
    exit 1
fi
if [ ! -d "$BACKUP_DIR" ]; then
    log_error "备份目录未挂载，拒绝写入同盘目录"
    exit 2
fi
if [ ! -f "$KEY_PATH" ]; then
    log_error "备份密钥文件不存在"
    exit 3
fi

DB_DEVICE="$(stat -c '%d' "$DB_PATH")"
BACKUP_DEVICE="$(stat -c '%d' "$BACKUP_DIR")"
if [ "$DB_DEVICE" = "$BACKUP_DEVICE" ]; then
    log_error "备份目录与数据库位于同一设备，拒绝继续"
    exit 4
fi

KEY_SIZE="$(stat -c '%s' "$KEY_PATH")"
KEY_MODE="$(stat -c '%a' "$KEY_PATH")"
if [ "$KEY_SIZE" -ne 32 ] || [ "$KEY_MODE" != "600" ]; then
    log_error "备份密钥必须是 32 字节且权限为 600"
    exit 5
fi

if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

umask 077
log_info "开始 AES-256-GCM 加密备份"
"$PYTHON_BIN" "$PROJECT_DIR/scripts/encrypted_backup.py" \
    --db "$DB_PATH" \
    --output "$BACKUP_FILE" \
    --key-file "$KEY_PATH"
chmod 600 "$BACKUP_FILE"
log_info "备份完成；保留期 30 天，过期文件由运维逐个审核清理"
