#!/bin/bash
# ============================================================
# 芸熙烘焙 — 生产数据安全拉取脚本（本地执行）
#
# 用途：
#   为离线检索评测（scripts/eval_retrieval.py）准备一份贴近线上的
#   知识库 + 商品数据快照。仅拉取检索评测所需数据，并在本地脱敏，
#   清除顾客 PII（messages / youzan_orders 等），避免敏感数据落地。
#
# 安全设计：
#   1. 服务器侧用 SQLite 官方 .backup 生成一致快照（WAL 安全，只读，不停机）
#   2. 原始快照只作为本地临时输入，不作为评测产物
#   3. Python 导出器只创建允许表和允许列，遇到未知表或敏感值即失败
#   4. 产物位于 data/（已被 .gitignore 忽略），不会进入版本库
#
# 用法：
#   bash scripts/pull_prod_snapshot.sh
#
# 环境变量（与 deploy.sh 对齐，可覆盖）：
#   SSH_HOST / SSH_USER / SSH_PORT / SSH_KEY
# ============================================================

set -euo pipefail

# ---- 服务器连接配置（默认值与 deploy.sh 一致）----
SSH_HOST="${SSH_HOST:-47.94.102.250}"
SSH_USER="${SSH_USER:-root}"
SSH_PORT="${SSH_PORT:-22}"
SSH_KEY="${SSH_KEY:-/mnt/c/Users/srafy/.ssh/id_ed25519}"
REMOTE_DIR="/opt/apps/yunxibakebot"
REMOTE_DB="${REMOTE_DIR}/data/bot.db"

# ---- 本地路径 ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SNAPSHOT_DIR="$PROJECT_DIR/data/prod_snapshot"
RAW_SNAPSHOT="$SNAPSHOT_DIR/.bot_raw.snapshot.db" # 仅用于导出过程的临时原始快照
EVAL_DB="$SNAPSHOT_DIR/eval.db"                   # 脱敏后供评测使用的库
REMOTE_TMP="/tmp/yunxi_eval_snapshot_$$.db"

CONNECT_TIMEOUT=10

# ---- 参数解析 ----
for arg in "$@"; do
    case "$arg" in
        -h|--help)
            echo "用法: bash scripts/pull_prod_snapshot.sh"
            echo "  从生产快照导出仅含允许表和允许列的 eval.db；不支持原始快照模式。"
            exit 0
            ;;
        *)
            echo "不支持的参数: $arg" >&2
            exit 2
            ;;
    esac
done

log_info()  { echo "[$(date '+%H:%M:%S')] [INFO] $*"; }
log_warn()  { echo "[$(date '+%H:%M:%S')] [WARN] $*"; }
log_error() { echo "[$(date '+%H:%M:%S')] [ERROR] $*" >&2; }

# ---- WSL 兼容：修复密钥权限（同 deploy.sh）----
TMP_SSH_KEY=""
if [[ "$SSH_KEY" == /mnt/c/* || "${OSTYPE:-}" == "msys" ]]; then
    TMP_SSH_KEY="/tmp/pull_ssh_key_$$"
    cp "$SSH_KEY" "$TMP_SSH_KEY"
    chmod 600 "$TMP_SSH_KEY"
    SSH_KEY="$TMP_SSH_KEY"
fi

cleanup() {
    [ -n "$TMP_SSH_KEY" ] && rm -f "$TMP_SSH_KEY" 2>/dev/null || true
    rm -f "$RAW_SNAPSHOT" 2>/dev/null || true
}
trap cleanup EXIT

ssh_run() {
    ssh -i "$SSH_KEY" -p "$SSH_PORT" \
        -o ConnectTimeout=$CONNECT_TIMEOUT \
        -o StrictHostKeyChecking=accept-new \
        "${SSH_USER}@${SSH_HOST}" "$@"
}

echo ""
echo "============================================"
echo "  生产数据安全拉取（仅检索评测用，本地脱敏）"
echo "============================================"
echo ""

mkdir -p "$SNAPSHOT_DIR"

# ============================================================
# Phase 1: 服务器侧生成一致快照（.backup，WAL 安全，只读）
# ============================================================
log_info "Phase 1/4: 在服务器上用 sqlite3 .backup 生成一致快照..."
if ! ssh_run "test -f '$REMOTE_DB'"; then
    log_error "服务器数据库不存在: $REMOTE_DB"
    exit 1
fi
# .backup 对在线 WAL 库生成一致副本，不停机、不锁写、纯只读
if ! ssh_run "sqlite3 '$REMOTE_DB' \".backup '$REMOTE_TMP'\" && sqlite3 '$REMOTE_TMP' 'PRAGMA integrity_check;' >/dev/null"; then
    log_error "服务器快照生成或完整性校验失败"
    ssh_run "rm -f '$REMOTE_TMP'" || true
    exit 1
fi
log_info "✓ 服务器快照已生成并通过完整性校验"

# ============================================================
# Phase 2: 拉取快照到本地
# ============================================================
log_info "Phase 2/4: 拉取快照到本地 $RAW_SNAPSHOT ..."
if ! scp -i "$SSH_KEY" -P "$SSH_PORT" \
        -o ConnectTimeout=$CONNECT_TIMEOUT \
        -o StrictHostKeyChecking=accept-new \
        "${SSH_USER}@${SSH_HOST}:${REMOTE_TMP}" "$RAW_SNAPSHOT"; then
    log_error "快照拉取失败"
    ssh_run "rm -f '$REMOTE_TMP'" || true
    exit 1
fi
# 清理服务器临时快照，避免敏感数据滞留
ssh_run "rm -f '$REMOTE_TMP'" || log_warn "服务器临时快照清理失败，请手动删除: $REMOTE_TMP"
log_info "✓ 快照已拉取到本地"

log_info "Phase 3/4: 使用白名单导出器生成评测库 $EVAL_DB ..."
rm -f "$EVAL_DB"
python3 "$PROJECT_DIR/scripts/export_safe_snapshot.py" "$RAW_SNAPSHOT" "$EVAL_DB"
KB_COUNT=$(sqlite3 "$EVAL_DB" "SELECT COUNT(*) FROM knowledge_base WHERE is_active=1;")
PROD_COUNT=$(sqlite3 "$EVAL_DB" "SELECT COUNT(*) FROM youzan_products;")
FINAL_DB="$EVAL_DB"
log_info "✓ 白名单导出完成：启用知识=$KB_COUNT | 商品=$PROD_COUNT"

# ============================================================
# Phase 4: 报告
# ============================================================
echo ""
echo "============================================"
echo "  ✓ 评测数据准备完成"
echo ""
echo "  评测库:      $FINAL_DB"
echo "  启用知识:    $KB_COUNT 条"
echo "  商品:        $PROD_COUNT 条"
echo ""
echo "  下一步:"
echo "    python scripts/eval_retrieval.py --db $FINAL_DB"
echo "============================================"
