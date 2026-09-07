#!/bin/bash
set -Eeuo pipefail

# ============================================================
# 服务器端部署脚本（由 deploy.sh 通过 SSH 远程调用）
# 职责：合入代码 → 停服务 → 替换数据 → 启服务 → 验证
# 健康检查失败自动回滚上一版本并复验；回滚幂等，可重复执行。
# 切换版本或停止服务后的任一失败经统一 ERR trap 自动恢复：
# 恢复上一 commit → 重启旧服务 → 健康复验 → 明确输出结果。
# 环境变量可覆盖，便于发布演练：PROJECT_DIR / SERVICE_NAME /
# HEALTH_URL / READY_URL / MAX_WAIT / ROLLBACK_VERIFY_WAIT。
# ============================================================

PROJECT_DIR="${PROJECT_DIR:-/opt/apps/yunxibakebot}"
SERVICE_NAME="${SERVICE_NAME:-yunxibakebot}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:7001/health}"
READY_URL="${READY_URL:-http://127.0.0.1:7001/ready}"
MAX_WAIT="${MAX_WAIT:-60}"
ROLLBACK_VERIFY_WAIT="${ROLLBACK_VERIFY_WAIT:-15}"

# 部署阶段状态：ERR trap 依据它们决定是否需要自动恢复
PREVIOUS_COMMIT=""
CODE_SWITCHED="no"
SERVICE_WAS_ACTIVE="unknown"
SERVICE_STOPPED_BY_DEPLOY="no"
ROLLBACK_IN_PROGRESS="no"
DEPLOY_SUCCEEDED="no"

log_info() {
    echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_error() {
    echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $1" >&2
}

# 统一清理临时产物：正常与失败路径均执行
cleanup_temp_files() {
    rm -f "$PROJECT_DIR/server.bundle"
}

# 统一失败恢复：脚本以非零退出结束、且已切换版本或停止服务时，
# 自动恢复上一版本旧服务并复验；显式退出与 set -e 路径统一覆盖。
# 回滚结果以结构化标记输出；回滚失败退出码 3 并写告警文件。
on_script_exit() {
    local exit_code="$?"
    cleanup_temp_files
    if [ "$exit_code" = "0" ] || [ "$DEPLOY_SUCCEEDED" = "yes" ]; then
        return 0
    fi
    if [ "$ROLLBACK_IN_PROGRESS" = "yes" ]; then
        return 0
    fi
    if [ "$CODE_SWITCHED" != "yes" ] && [ "$SERVICE_STOPPED_BY_DEPLOY" != "yes" ]; then
        return 0
    fi
    ROLLBACK_IN_PROGRESS="yes"
    log_error "❌ 部署失败自动回滚恢复"
    if [ -z "$PREVIOUS_COMMIT" ]; then
        log_error "无可用的上一版本记录，请人工介入"
        return 0
    fi
    if rollback_release "$PREVIOUS_COMMIT"; then
        echo "ROLLBACK_STATUS=success"
        log_error "已自动恢复上一版本，发布失败请排查后重试"
    else
        echo "ROLLBACK_STATUS=failed"
        emit_rollback_alert "部署失败且自动回滚未恢复服务"
        log_error "自动回滚未恢复服务，请人工介入"
        exit 3
    fi
}
trap on_script_exit EXIT

# 回滚失败告警：写机器可读告警文件并给出人工指引（不止于日志）
emit_rollback_alert() {
    local reason="$1"
    local alert_log="${ALERT_LOG:-$PROJECT_DIR/deploy-alerts.log}"
    echo "$(date '+%Y-%m-%d %H:%M:%S') ALERT service=${SERVICE_NAME} reason=${reason}" >> "$alert_log" 2>/dev/null || true
    log_error "❌❌ 已写入回滚失败告警: ${alert_log}；请人工介入: journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
}

# 查询发布前服务状态：active / inactive / unknown 三态。
# 查询命令失败或返回非预期值一律判 unknown，不得降级为 inactive。
query_predeploy_service_state() {
    local active_state
    if ! active_state=$(systemctl show "$SERVICE_NAME" --property=ActiveState --value 2>/dev/null); then
        echo "unknown"
        return 0
    fi
    active_state=$(printf '%s' "$active_state" | tr -d '[:space:]')
    case "$active_state" in
        active) echo "active" ;;
        inactive) echo "inactive" ;;
        *) echo "unknown" ;;
    esac
}

# 等待健康与就绪，返回 0 表示通过
wait_for_healthy() {
    local limit="$1"
    local elapsed=0
    while [ "$elapsed" -lt "$limit" ]; do
        health_status=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")
        ready_status=$(curl -s -o /dev/null -w "%{http_code}" "$READY_URL" 2>/dev/null || echo "000")
        if [ "$health_status" = "200" ] && [ "$ready_status" = "200" ]; then
            log_info "✓ 服务健康/就绪检查通过 (HTTP 200, 耗时 ${elapsed}s)"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
    done
    return 1
}

# 按发布前状态恢复服务：运行过则重启复验，确认停止则保持停止。
# 状态未知（发布在记录前失败）时保守重启复验，避免带病运行；
# 停止状态不是失败，调用方按返回值区分复验结果。
restore_service_state() {
    if [ "$SERVICE_WAS_ACTIVE" = "no" ]; then
        systemctl stop "$SERVICE_NAME" 2>/dev/null || true
        echo "SERVICE_RESTORE_STATUS=inactive"
        return 0
    fi
    if [ "$SERVICE_WAS_ACTIVE" = "unknown" ]; then
        log_error "发布前服务状态未知，保守重启复验"
    fi
    systemctl restart "$SERVICE_NAME"
    wait_for_healthy "$ROLLBACK_VERIFY_WAIT"
    return $?
}

# 幂等回滚到指定提交：已在目标提交时只恢复服务状态并复验
rollback_release() {
    local previous="$1"
    ROLLBACK_IN_PROGRESS="yes"
    log_error "开始回滚到 ${previous}"
    cd "$PROJECT_DIR"
    current_commit=$(git rev-parse HEAD)
    if [ "$current_commit" = "$previous" ]; then
        log_info "已位于回滚点，仅恢复服务状态并复验"
    else
        git reset --hard "$previous"
        log_info "✓ 代码已切回 ${previous}"
    fi
    if restore_service_state; then
        log_info "✓ 回滚后服务状态已恢复 (RTO <= ${ROLLBACK_VERIFY_WAIT}s)"
        return 0
    fi
    log_error "❌ 回滚后服务仍未就绪，请人工介入: journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
    return 1
}

# ---- Step 0: 发布前检查（目录、版本记录、工作区、服务状态） ----
# 状态未知直接拒绝，未切换版本、不操作服务；active/inactive 记录后供
# 停止与回滚使用，全程不再重新判断。
cd "$PROJECT_DIR"
PREVIOUS_COMMIT=$(git rev-parse HEAD)

log_info "检查生产工作区是否干净..."
tracked_dirty=$(git status --porcelain --untracked-files=no)
other_untracked=$(git status --porcelain --untracked-files=normal | grep '^??' | grep -v '^?? server.bundle$' | grep -v '^?? .env$' | grep -v '^?? deploy-alerts.log$' || true)
if [ -n "$tracked_dirty" ] || [ -n "$other_untracked" ]; then
    log_error "生产工作区非干净，拒绝发布；请先处理未提交改动"
    exit 1
fi
log_info "✓ 生产工作区干净"

log_info "确认发布前服务状态..."
PREDEPLOY_STATE=$(query_predeploy_service_state)
case "$PREDEPLOY_STATE" in
    active)
        SERVICE_WAS_ACTIVE="yes"
        log_info "✓ 发布前服务运行中"
        ;;
    inactive)
        SERVICE_WAS_ACTIVE="no"
        log_info "✓ 发布前服务已停止"
        ;;
    *)
        log_error "无法确认发布前服务状态，拒绝继续发布"
        exit 1
        ;;
esac

# ---- Step 1: 合入 Git bundle ----
log_info "正在合入代码..."

if [ ! -f "server.bundle" ]; then
    log_error "server.bundle 不存在！请确认本地已传输成功"
    exit 1
fi

git fetch server.bundle '+HEAD:refs/remotes/bundle/master' 2>/dev/null || {
    log_error "git fetch 失败，bundle 可能损坏"
    exit 1
}

git reset --hard bundle/master
CODE_SWITCHED="yes"
log_info "✓ 代码合入成功 (commit: $(git rev-parse --short HEAD))"

# ---- Step 2: 启动安全配置预检 ----
log_info "检查启动安全配置..."
if [ ! -f ".env" ] \
    || ! grep -Eq '^ADMIN_API_TOKEN=.+$' .env \
    || ! grep -Eq '^ADMIN_SESSION_SECRET=.+$' .env; then
    log_error "启动安全配置缺失；拒绝停止现有服务"
    exit 1
fi
log_info "✓ 启动安全配置已就绪"

# ---- Step 3: 安装/更新依赖 ----
log_info "检查 Python 依赖..."
if git diff --name-only HEAD~1 HEAD 2>/dev/null | grep -q "requirements.txt"; then
    log_info "检测到 requirements.txt 变化，执行 pip install..."
    # 使用 --quiet 减少输出，只显示错误
    pip install --quiet -r requirements.txt
    log_info "✓ 依赖更新完成"
else
    log_info "依赖无变化，跳过安装"
fi

# ---- Step 4: 停止服务（以发布前记录为准，不再重新查询） ----
log_info "停止服务 ${SERVICE_NAME}..."
if [ "$SERVICE_WAS_ACTIVE" = "yes" ]; then
    systemctl stop "$SERVICE_NAME"
    SERVICE_STOPPED_BY_DEPLOY="yes"
    sleep 2
    log_info "✓ 服务已停止"
else
    log_info "⚠ 发布前服务未运行，跳过停止"
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

# ---- Step 7: 健康检查（等待就绪，失败自动回滚）----
log_info "等待服务就绪 (最多 ${MAX_WAIT}s)..."
if wait_for_healthy "$MAX_WAIT"; then
    log_info "✓ 新版本已上线"
    DEPLOY_SUCCEEDED="yes"
else
    log_error "❌ 服务在 ${MAX_WAIT}s 内未就绪，自动回滚到 ${PREVIOUS_COMMIT}"
    if rollback_release "$PREVIOUS_COMMIT"; then
        echo "ROLLBACK_STATUS=success"
        log_error "已自动恢复上一版本，发布失败请排查后重试"
        exit 1
    else
        echo "ROLLBACK_STATUS=failed"
        emit_rollback_alert "新版本未就绪且自动回滚未恢复服务"
        log_error "自动回滚未恢复服务，请人工介入"
        exit 3
    fi
fi

# ---- 完成 ----
echo "DEPLOY_STATUS=success"
echo ""
echo "============================================"
echo "  部署完成！版本: $(cat VERSION 2>/dev/null || echo 'unknown')"
echo "  Commit:   $(git rev-parse --short HEAD)"
echo "  时间:     $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"
