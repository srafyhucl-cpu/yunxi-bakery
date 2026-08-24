#!/bin/bash
# ============================================================
# 芸熙烘焙 AI 客服 — 一键部署脚本（本地执行）
#
# 用法：
#   1. 配置下方服务器连接信息（或通过环境变量传入）
#   2. 执行: bash scripts/deploy.sh
#   3. 脚本自动完成：打包→传输→部署；不自动递归清理工作区
#
# 环境变量（可选覆盖默认值）：
#   SSH_HOST    - 服务器地址
#   SSH_USER    - SSH 用户名
#   SSH_PORT    - SSH 端口 (默认 22)
#   SSH_KEY     - SSH 私钥路径 (默认 ~/.ssh/id_rsa)
# ============================================================

set -euo pipefail

# ---- 配置区 ----
SSH_HOST="${SSH_HOST:-47.94.102.250}"
SSH_USER="${SSH_USER:-root}"
SSH_PORT="${SSH_PORT:-22}"
SSH_KEY="${SSH_KEY:-/mnt/c/Users/srafy/.ssh/id_ed25519}"
REMOTE_DIR="/opt/apps/yunxibakebot"
BUNDLE_FILE="server.bundle"
MAX_RETRY=3
CONNECT_TIMEOUT=10

# ---- WSL 兼容：修复密钥权限 ----
# Windows 文件系统上密钥权限为 0777，SSH 拒绝使用
# 解决方案：复制到 /tmp 并设为 600
TMP_SSH_KEY=""
if [[ "$SSH_KEY" == /mnt/c/* || "$OSTYPE" == "msys" ]]; then
    TMP_SSH_KEY="/tmp/deploy_ssh_key_$$"
    cp "$SSH_KEY" "$TMP_SSH_KEY"
    chmod 600 "$TMP_SSH_KEY"
    SSH_KEY="$TMP_SSH_KEY"
fi

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%H:%M:%S') $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%H:%M:%S') $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%H:%M:%S') $1" >&2
}

# ---- 工具函数 ----

# 带重试的 SCP 传输
scp_with_retry() {
    local src="$1" dst="$2"
    local attempt=1

    while [ $attempt -le $MAX_RETRY ]; do
        log_info "传输文件 (第 ${attempt}/${MAX_RETRY} 次)..."
        if scp -i "$SSH_KEY" \
               -P "$SSH_PORT" \
               -o ConnectTimeout=$CONNECT_TIMEOUT \
               -o StrictHostKeyChecking=accept-new \
               "$src" "${SSH_USER}@${SSH_HOST}:${dst}"; then
            return 0
        fi
        log_error "传输失败，等待 5s 后重试..."
        sleep 5
        attempt=$((attempt + 1))
    done
    return 1
}

# 带重试的 SSH 远程执行
ssh_with_retry() {
    local cmd="$1"
    local attempt=1

    while [ $attempt -le $MAX_RETRY ]; do
        log_info "远程执行命令 (第 ${attempt}/${MAX_RETRY} 次)..."
        if ssh -i "$SSH_KEY" \
              -p "$SSH_PORT" \
              -o ConnectTimeout=$CONNECT_TIMEOUT \
              -o StrictHostKeyChecking=accept-new \
              "${SSH_USER}@${SSH_HOST}" "$cmd"; then
            return 0
        fi
        log_error "远程执行失败，等待 5s 后重试..."
        sleep 5
        attempt=$((attempt + 1))
    done
    return 1
}

# ============================================================
# Phase 0: 前置检查
# ============================================================
echo ""
echo "============================================"
echo "  芸熙烘焙 AI 客服 — 自动部署工具"
echo "============================================"
echo ""

START_TIME=$(date +%s)

# 检查 Git 仓库状态
log_info "检查工作区状态..."
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    log_warn "工作区有未提交的变更，将使用当前代码进行部署"
fi

# 获取版本信息
VERSION=$(cat VERSION 2>/dev/null || echo "unknown")
COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")

log_info "版本: ${VERSION} | Commit: ${COMMIT} | 分支: ${BRANCH}"

# 检查 SSH 连接
log_info "测试 SSH 连接 (${SSH_USER}@${SSH_HOST}:${SSH_PORT})..."
if ! ssh -i "$SSH_KEY" \
         -p "$SSH_PORT" \
         -o ConnectTimeout=$CONNECT_TIMEOUT \
         -o BatchMode=yes \
         -o StrictHostKeyChecking=accept-new \
         "${SSH_USER}@${SSH_HOST}" "exit 0"; then
    log_error "SSH 连接失败！请检查："
    log_error "  1. 服务器地址是否正确: ${SSH_HOST}"
    log_error "  2. SSH 密钥是否存在: ${SSH_KEY}"
    log_error "  3. 密钥是否已添加到服务器的 authorized_keys"
    exit 1
fi
log_info "✓ SSH 连接正常"

# ============================================================
# Phase 1: 打包 Git Bundle
# ============================================================
echo ""
log_info "Phase 1/5: 创建 Git Bundle..."

rm -f "$BUNDLE_FILE"

git bundle create "$BUNDLE_FILE" --all

BUNDLE_SIZE=$(du -h "$BUNDLE_FILE" | cut -f1)
log_info "✓ Bundle 创建完成 (${BUNDLE_SIZE})"

# ============================================================
# Phase 2: 传输到服务器
# ============================================================
echo ""
log_info "Phase 2/5: 传输文件到服务器..."

if ! scp_with_retry "$BUNDLE_FILE" "${REMOTE_DIR}/"; then
    log_error "文件传输失败！请检查网络连接和磁盘空间"
    rm -f "$BUNDLE_FILE"
    exit 1
fi

log_info "✓ 文件传输完成"

# 删除本地 bundle（节省空间）
rm -f "$BUNDLE_FILE"

# ============================================================
# Phase 3: 远程执行部署
# ============================================================
echo ""
log_info "Phase 3/5: 在服务器上执行部署..."

# 先上传最新的 deploy_server.sh
log_info "上传 deploy_server.sh..."
if ! scp_with_retry "scripts/deploy_server.sh" "${REMOTE_DIR}/scripts/deploy_server.sh"; then
    log_error "deploy_server.sh 上传失败"
    exit 1
fi

# 远程执行
if ! ssh_with_retry "cd ${REMOTE_DIR} && bash scripts/deploy_server.sh"; then
    log_error "服务器端部署失败！请手动排查:"
    log_error "  ssh ${SSH_USER}@${SSH_HOST} -p ${SSH_PORT}"
    log_error "  journalctl -u yunxibakebot -n 50 --no-pager"
    exit 1
fi

log_info "✓ 服务器部署完成"

# ============================================================
# Phase 4: 输出部署结果
# ============================================================
echo ""
log_info "Phase 4/4: 跳过工作区递归清理（按项目删除红线执行）"
log_info "部署脚本只删除自身明确创建的 bundle 和临时密钥文件"

# ============================================================
# 输出报告
# ============================================================
END_TIME=$(date +%s)
DURATION=$(( END_TIME - START_TIME ))

echo ""
echo "============================================"
echo "  🎉 部署成功！"
echo ""
echo "  版本:     v${VERSION}"
echo "  Commit:   ${COMMIT}"
echo "  分支:     ${BRANCH}"
echo "  服务器:   ${SSH_HOST}"
echo "  耗时:     ${DURATION}s"
echo "  时间:     $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "  访问:     https://yunxifood.cn/health"
echo "============================================"

# ---- 清理临时密钥 ----
if [ -n "$TMP_SSH_KEY" ]; then
    rm -f "$TMP_SSH_KEY"
fi
