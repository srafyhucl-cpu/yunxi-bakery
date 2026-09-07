#!/bin/bash
# 发布回滚演练：桩隔离验证部署成功与失败自动回滚路径。
# 用法：bash scripts/drill_deploy_rollback.sh
# 不触碰生产目录与真实服务，全部在临时目录执行，可重复运行。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/bin" "$WORK/proj/data"
cat > "$WORK/bin/systemctl" <<'EOF'
#!/bin/bash
echo "$*" >> "$STUB_LOG"
case "${STUB_SERVICE_STATE:-active}" in
    active) active_state="active" ;;
    inactive) active_state="inactive" ;;
    *) active_state="" ;;
esac
if [ "$1" = "show" ]; then
    if [ -z "$active_state" ]; then
        exit 2
    fi
    echo "$active_state"
    exit 0
fi
if [ "$1" = "is-active" ]; then
    if [ "$active_state" = "active" ]; then
        exit 0
    fi
    exit 3
fi
if [ "${STUB_FAIL_START:-0}" = "1" ]; then
    case "$1" in
        start) exit 1;;
    esac
fi
exit 0
EOF
cat > "$WORK/bin/curl" <<'EOF'
#!/bin/bash
if [ "${CURL_CODE:-000}" = "200" ]; then
    printf "200"
else
    printf "000"
fi
exit 0
EOF
cat > "$WORK/bin/pip" <<'EOF'
#!/bin/bash
echo "$*" >> "$STUB_LOG"
exit "${STUB_FAIL_PIP:-0}"
EOF
chmod +x "$WORK/bin"/*
export PATH="$WORK/bin:$PATH"
export STUB_LOG="$WORK/systemctl.log"

git init -q "$WORK/proj"
cd "$WORK/proj"
git config user.email "drill@example.com"
git config user.name "drill"
git config commit.gpgsign false
echo "v1" > VERSION
git add VERSION
git commit -qm "v1"
V1=$(git rev-parse HEAD)
echo "v2" > VERSION
git commit -qam "v2"
git bundle create server.bundle HEAD~1..HEAD >/dev/null 2>&1 || git bundle create server.bundle HEAD
git reset -q --hard "$V1"
printf 'ADMIN_API_TOKEN=x\nADMIN_SESSION_SECRET=y\n' > .env

export PROJECT_DIR="$WORK/proj"
export SERVICE_NAME="drill-service"
export HEALTH_URL="http://127.0.0.1:9/health"
export READY_URL="http://127.0.0.1:9/ready"
export MAX_WAIT=3
export ROLLBACK_VERIFY_WAIT=3

echo "--- 演练 1：健康持续失败，期望自动回滚到 v1 ---"
export CURL_CODE="000"
code=0
bash "$BACKEND_DIR/scripts/deploy_server.sh" > "$WORK/fail.log" 2>&1 || code="$?"
if [ "$code" != "3" ]; then
    echo "演练 1 失败：期望退出码 3（回滚未恢复需人工），实际 $code"
    exit 1
fi
HEAD_AFTER_FAIL=$(git rev-parse HEAD)
if [ "$HEAD_AFTER_FAIL" != "$V1" ]; then
    echo "演练 1 失败：回滚后 HEAD=$HEAD_AFTER_FAIL，期望 $V1"
    exit 1
fi
grep -q "自动回滚" "$WORK/fail.log" || { echo "演练 1 失败：缺少自动回滚记录"; exit 1; }
grep -q "ROLLBACK_STATUS=failed" "$WORK/fail.log" || { echo "演练 1 失败：缺少结构化回滚标记"; exit 1; }
grep -q "restart" "$STUB_LOG" || { echo "演练 1 失败：回滚未操作服务"; exit 1; }
[ -f "$WORK/proj/deploy-alerts.log" ] || { echo "演练 1 失败：缺少回滚失败告警文件"; exit 1; }
echo "演练 1 通过：失败自动回滚，HEAD 已恢复 v1"

echo "--- 演练 2：重复失败发布，回滚幂等可重复执行 ---"
echo "v2-retry" > VERSION
git commit -qam "v2-retry"
git bundle create server.bundle "$V1"..HEAD >/dev/null
git reset -q --hard "$V1"
export CURL_CODE="000"
code=0
bash "$BACKEND_DIR/scripts/deploy_server.sh" > "$WORK/fail2.log" 2>&1 || code="$?"
if [ "$code" != "3" ]; then
    echo "演练 2 失败：期望退出码 3，实际 $code"
    exit 1
fi
if [ "$(git rev-parse HEAD)" != "$V1" ]; then
    echo "演练 2 失败：重复回滚后 HEAD 偏离 v1"
    exit 1
fi
grep -q "自动回滚" "$WORK/fail2.log" || { echo "演练 2 失败：缺少自动回滚记录"; exit 1; }
grep -q "ROLLBACK_STATUS=failed" "$WORK/fail2.log" || { echo "演练 2 失败：缺少结构化回滚标记"; exit 1; }
echo "演练 2 通过：回滚幂等，可重复执行"

echo "--- 演练 3：健康正常，期望一次上线成功 ---"
echo "v3" > VERSION
git commit -qam "v3"
git bundle create server.bundle HEAD~1..HEAD >/dev/null 2>&1 || git bundle create server.bundle HEAD
export CURL_CODE="200"
if ! bash "$BACKEND_DIR/scripts/deploy_server.sh" > "$WORK/ok.log" 2>&1; then
    echo "演练 3 失败：健康正常时期望成功"
    cat "$WORK/ok.log"
    exit 1
fi
grep -q "部署完成" "$WORK/ok.log" || { echo "演练 3 失败：缺少完成标记"; exit 1; }
echo "演练 3 通过：健康路径一次上线成功"

echo "--- 演练 4：服务启动失败，期望自动恢复旧版本旧服务 ---"
echo "v4-start" > VERSION
git commit -qam "v4-start"
git bundle create server.bundle HEAD~1..HEAD >/dev/null 2>&1 || git bundle create server.bundle HEAD
git reset -q --hard "$V1"
export STUB_FAIL_START=1
export CURL_CODE="000"
code=0
bash "$BACKEND_DIR/scripts/deploy_server.sh" > "$WORK/start-fail.log" 2>&1 || code="$?"
if [ "$code" != "3" ]; then
    echo "演练 4 失败：期望退出码 3，实际 $code"
    exit 1
fi
if [ "$(git rev-parse HEAD)" != "$V1" ]; then
    echo "演练 4 失败：启动失败后 HEAD 未恢复 v1"
    exit 1
fi
grep -q "自动回滚" "$WORK/start-fail.log" || { echo "演练 4 失败：缺少自动回滚记录"; exit 1; }
grep -q "ROLLBACK_STATUS=failed" "$WORK/start-fail.log" || { echo "演练 4 失败：缺少结构化回滚标记"; exit 1; }
grep -q "restart" "$STUB_LOG" || { echo "演练 4 失败：回滚未重启服务"; exit 1; }
export STUB_FAIL_START=0
echo "演练 4 通过：启动失败自动恢复，HEAD 已恢复 v1"

echo "--- 演练 5：数据临时文件阻断，期望自动恢复不丢服务 ---"
echo "v5-tmp" > VERSION
git commit -qam "v5-tmp"
git bundle create server.bundle HEAD~1..HEAD >/dev/null 2>&1 || git bundle create server.bundle HEAD
git reset -q --hard "$V1"
touch "$WORK/proj/data/bot.db.tmp"
export CURL_CODE="000"
code=0
bash "$BACKEND_DIR/scripts/deploy_server.sh" > "$WORK/tmp-fail.log" 2>&1 || code="$?"
if [ "$code" != "1" ]; then
    echo "演练 5 失败：期望退出码 1（发布前拒绝），实际 $code"
    exit 1
fi
if [ "$(git rev-parse HEAD)" != "$V1" ]; then
    echo "演练 5 失败：拒绝发布后 HEAD 不应变化"
    exit 1
fi
grep -q "非干净" "$WORK/tmp-fail.log" || { echo "演练 5 失败：缺少工作区保护记录"; exit 1; }
if grep -q "ROLLBACK_STATUS" "$WORK/tmp-fail.log"; then
    echo "演练 5 失败：未切换版本不应触发回滚"
    exit 1
fi
[ -f "$WORK/proj/data/bot.db.tmp" ] || { echo "演练 5 失败：回滚误删数据临时文件"; exit 1; }
rm -f "$WORK/proj/data/bot.db.tmp"
echo "演练 5 通过：临时文件阻断自动恢复，数据文件未被删除"

echo "--- 演练 6：依赖安装失败，期望自动恢复 ---"
echo "v4" > VERSION
echo "# drill-dep" >> requirements.txt
git add VERSION requirements.txt
git commit -qm "v4-deps"
git bundle create server.bundle "$V1"..HEAD >/dev/null
git reset -q --hard "$V1"
export STUB_FAIL_PIP=1
export CURL_CODE="000"
code=0
bash "$BACKEND_DIR/scripts/deploy_server.sh" > "$WORK/pip-fail.log" 2>&1 || code="$?"
if [ "$code" != "3" ]; then
    echo "演练 6 失败：期望退出码 3，实际 $code"
    exit 1
fi
if [ "$(git rev-parse HEAD)" != "$V1" ]; then
    echo "演练 6 失败：依赖失败后 HEAD 未恢复 v1"
    exit 1
fi
grep -q "自动回滚" "$WORK/pip-fail.log" || { echo "演练 6 失败：缺少自动回滚记录"; exit 1; }
grep -q "ROLLBACK_STATUS=failed" "$WORK/pip-fail.log" || { echo "演练 6 失败：缺少结构化回滚标记"; exit 1; }
export STUB_FAIL_PIP=0
echo "演练 6 通过：依赖失败自动恢复，HEAD 已恢复 v1"

echo "--- 演练 7：启动失败但回滚复验通过，期望恢复并退出码 1 ---"
echo "v7-start" > VERSION
git commit -qam "v7-start"
git bundle create server.bundle HEAD~1..HEAD >/dev/null 2>&1 || git bundle create server.bundle HEAD
git reset -q --hard "$V1"
export STUB_FAIL_START=1
export CURL_CODE="200"
code=0
bash "$BACKEND_DIR/scripts/deploy_server.sh" > "$WORK/recovered.log" 2>&1 || code="$?"
if [ "$code" != "1" ]; then
    echo "演练 7 失败：期望退出码 1（已恢复但发布失败），实际 $code"
    exit 1
fi
if [ "$(git rev-parse HEAD)" != "$V1" ]; then
    echo "演练 7 失败：恢复后 HEAD 未回到 v1"
    exit 1
fi
grep -q "ROLLBACK_STATUS=success" "$WORK/recovered.log" || { echo "演练 7 失败：缺少恢复成功标记"; exit 1; }
export STUB_FAIL_START=0
echo "演练 7 通过：回滚恢复成功，发布失败退出码 1"

echo "--- 演练 8：工作区非干净，期望拒绝发布且不切换版本 ---"
echo "v8" > VERSION
git commit -qam "v8"
git bundle create server.bundle HEAD~1..HEAD >/dev/null 2>&1 || git bundle create server.bundle HEAD
git reset -q --hard "$V1"
echo "hotfix" > "$WORK/proj/HOTFIX.tmp"
export CURL_CODE="200"
code=0
bash "$BACKEND_DIR/scripts/deploy_server.sh" > "$WORK/dirty.log" 2>&1 || code="$?"
if [ "$code" = "0" ]; then
    echo "演练 8 失败：非干净工作区时期望拒绝发布"
    exit 1
fi
if [ "$(git rev-parse HEAD)" != "$V1" ]; then
    echo "演练 8 失败：拒绝发布后 HEAD 不应变化"
    exit 1
fi
grep -q "非干净" "$WORK/dirty.log" || { echo "演练 8 失败：缺少工作区保护记录"; exit 1; }
if grep -q "ROLLBACK_STATUS" "$WORK/dirty.log"; then
    echo "演练 8 失败：未切换版本不应触发回滚"
    exit 1
fi
rm -f "$WORK/proj/HOTFIX.tmp"
echo "演练 8 通过：非干净工作区拒绝发布，版本未动"

echo "--- 演练 9：发布前服务未运行，期望回滚后保持停止 ---"
echo "v9" > VERSION
git commit -qam "v9"
git bundle create server.bundle HEAD~1..HEAD >/dev/null 2>&1 || git bundle create server.bundle HEAD
git reset -q --hard "$V1"
export STUB_SERVICE_STATE=inactive
export STUB_FAIL_START=1
export CURL_CODE="000"
stub_lines_before=$(wc -l < "$STUB_LOG")
code=0
bash "$BACKEND_DIR/scripts/deploy_server.sh" > "$WORK/inactive.log" 2>&1 || code="$?"
if [ "$code" != "1" ] && [ "$code" != "3" ]; then
    echo "演练 9 失败：期望退出码 1 或 3，实际 $code"
    exit 1
fi
if [ "$(git rev-parse HEAD)" != "$V1" ]; then
    echo "演练 9 失败：回滚后 HEAD 未回到 v1"
    exit 1
fi
grep -q "SERVICE_RESTORE_STATUS=inactive" "$WORK/inactive.log" || { echo "演练 9 失败：缺少停止状态恢复标记"; exit 1; }
stub_lines_after=$(wc -l < "$STUB_LOG")
stub_new=$(tail -n +"$((stub_lines_before + 1))" "$STUB_LOG")
if echo "$stub_new" | grep -Eq '^restart( |$)'; then
    echo "演练 9 失败：回滚错误启动了原本停止的服务"
    exit 1
fi
export STUB_SERVICE_STATE=active
export STUB_FAIL_START=0
echo "演练 9 通过：回滚后服务保持停止，版本已恢复 v1"

echo "--- 演练 10：状态查询失败，期望发布前拒绝且不切换版本 ---"
echo "v10" > VERSION
git commit -qam "v10"
git bundle create server.bundle HEAD~1..HEAD >/dev/null 2>&1 || git bundle create server.bundle HEAD
git reset -q --hard "$V1"
export STUB_SERVICE_STATE=unknown
export CURL_CODE="000"
stub_lines_before=$(wc -l < "$STUB_LOG")
code=0
bash "$BACKEND_DIR/scripts/deploy_server.sh" > "$WORK/unknown.log" 2>&1 || code="$?"
if [ "$code" = "0" ]; then
    echo "演练 10 失败：未知状态时期望拒绝发布"
    exit 1
fi
if [ "$(git rev-parse HEAD)" != "$V1" ]; then
    echo "演练 10 失败：拒绝发布后 HEAD 不应变化"
    exit 1
fi
grep -q "无法确认发布前服务状态" "$WORK/unknown.log" || { echo "演练 10 失败：缺少未知状态拒绝记录"; exit 1; }
if grep -q "ROLLBACK_STATUS" "$WORK/unknown.log"; then
    echo "演练 10 失败：未切换版本不应触发回滚"
    exit 1
fi
stub_new=$(tail -n +"$((stub_lines_before + 1))" "$STUB_LOG")
if echo "$stub_new" | grep -Eq '^(stop|start|restart)( |$)'; then
    echo "演练 10 失败：未知状态服务不得被操作"
    exit 1
fi
export STUB_SERVICE_STATE=active
echo "演练 10 通过：未知状态发布前拒绝，版本服务均未动"

echo "全部演练通过"
