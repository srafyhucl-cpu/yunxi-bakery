#!/bin/bash
set -euo pipefail

# ============================================================
# 服务器端部署脚本（由 deploy.sh 通过 SSH 远程调用）
# 职责：合入代码 → 停服务 → 替换数据 → 启服务 → 验证
# ============================================================

PROJECT_DIR="/opt/apps/yunxibakebot"
SERVICE_NAME="yunxibakebot"
HEALTH_URL="http://127.0.0.1:7001/health"
READY_URL="http://127.0.0.1:7001/ready"
MAX_WAIT=60

log_info() {
    echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_error() {
    echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $1" >&2
}

# ---- Step 1: 合入 Git bundle ----
log_info "正在合入代码..."
cd "$PROJECT_DIR"
PREVIOUS_COMMIT=$(git rev-parse HEAD)

if [ ! -f "server.bundle" ]; then
    log_error "server.bundle 不存在！请确认本地已传输成功"
    exit 1
fi

git fetch server.bundle HEAD:refs/remotes/bundle/master 2>/dev/null || {
    log_error "git fetch 失败，bundle 可能损坏"
    rm -f server.bundle
    exit 1
}

git reset --hard bundle/master
rm -f server.bundle
log_info "✓ 代码合入成功 (commit: $(git rev-parse --short HEAD))"

# ---- Step 3: 启动安全配置预检 ----
log_info "检查启动安全配置..."
if [ ! -f ".env" ] \
    || ! grep -Eq '^ADMIN_API_TOKEN=.+$' .env \
    || ! grep -Eq '^ADMIN_SESSION_SECRET=.+$' .env; then
    log_error "启动安全配置缺失；拒绝停止现有服务"
    exit 1
fi
log_info "✓ 启动安全配置已就绪"

# ---- Step 2: 安装/更新依赖 ----
log_info "检查 Python 依赖..."
if git diff --name-only HEAD~1 HEAD 2>/dev/null | grep -q "requirements.txt"; then
    log_info "检测到 requirements.txt 变化，执行 pip install..."
    # 使用 --quiet 减少输出，只显示错误
    pip install --quiet -r requirements.txt
    log_info "✓ 依赖更新完成"
else
    log_info "依赖无变化，跳过安装"
fi

# ---- Step 4: 停止服务 ----
log_info "停止服务 ${SERVICE_NAME}..."
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl stop "$SERVICE_NAME"
    sleep 2
    log_info "✓ 服务已停止"
else
    log_info "⚠ 服务未运行，跳过停止"
fi

# ---- Step 5: 数据库发布边界 ----
log_info "检查数据库临时文件..."

if [ -f "data/bot.db.tmp" ] || [ -f "data/embeddings.pkl.tmp" ]; then
    log_error "检测到未登记的数据临时文件；代码发布不自动覆盖生产数据"
    exit 1
fi

# ---- Step 6: 启动服务 ----
log_info "启动服务 ${SERVICE_NAME}..."
systemctl start "$SERVICE_NAME"
log_info "✓ 服务已启动"

# ---- Step 7: 健康检查（等待就绪）----
log_info "等待服务就绪 (最多 ${MAX_WAIT}s)..."
elapsed=0
while [ $elapsed -lt $MAX_WAIT ]; do
    health_status=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")
    ready_status=$(curl -s -o /dev/null -w "%{http_code}" "$READY_URL" 2>/dev/null || echo "000")
    if [ "$health_status" = "200" ] && [ "$ready_status" = "200" ]; then
        log_info "✓ 服务健康/就绪检查通过 (HTTP 200, 耗时 ${elapsed}s)"
        break
    fi
    sleep 3
    elapsed=$((elapsed + 3))
done

if [ $elapsed -ge $MAX_WAIT ]; then
    log_error "❌ 服务在 ${MAX_WAIT}s 内未就绪！请手动排查:"
    log_error "  journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
    log_error "  回滚点: ${PREVIOUS_COMMIT}"
    log_error "  回滚命令: cd ${PROJECT_DIR} && git reset --hard ${PREVIOUS_COMMIT} && systemctl restart ${SERVICE_NAME}"
    exit 1
fi

# ---- 完成 ----
echo ""
echo "============================================"
echo "  部署完成！版本: $(cat VERSION 2>/dev/null || echo 'unknown')"
echo "  Commit:   $(git rev-parse --short HEAD)"
echo "  时间:     $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"
