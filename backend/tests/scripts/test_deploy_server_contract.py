"""部署脚本发布边界合同测试。"""

from pathlib import Path


DEPLOY_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "deploy_server.sh"


def test_deploy_server_fails_fast_and_does_not_replace_tmp_data() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "pip install --quiet -r requirements.txt\n" in source
    assert "grep -Eq '^ADMIN_API_TOKEN=.+$' .env" in source
    assert "grep -Eq '^ADMIN_SESSION_SECRET=.+$' .env" in source
    assert "拒绝停止现有服务" in source
    assert 'if [ -f "data/bot.db.tmp" ]' in source
    assert "mv -f" not in source
    assert 'READY_URL="${READY_URL:-http://127.0.0.1:7001/ready}"' in source
    assert "ready_status=$(curl" in source
    assert "trap on_script_exit EXIT" in source
    assert "rollback_release" in source
    assert "+HEAD:refs/remotes/bundle/master" in source
    assert "CODE_SWITCHED" in source
    assert "SERVICE_STOPPED_BY_DEPLOY" in source
    assert "ROLLBACK_IN_PROGRESS" in source
    assert "DEPLOY_SUCCEEDED" in source
    assert "SERVICE_RESTORE_STATUS" in source
    assert "SERVICE_WAS_ACTIVE" in source
    assert "restore_service_state" in source
    assert "ActiveState" in source
    assert 'SERVICE_WAS_ACTIVE="unknown"' in source
    assert "无法确认发布前服务状态" in source
    assert "ROLLBACK_STATUS" in source


def test_bundle_deployment_targets_current_application_root() -> None:
    root = Path(__file__).resolve().parents[2]
    deploy_source = (root / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    deploy_server_source = (root / "scripts" / "deploy_server.sh").read_text(
        encoding="utf-8"
    )

    assert 'REMOTE_DIR="/opt/apps/yunxibakebot"' in deploy_source
    assert 'PROJECT_DIR="${PROJECT_DIR:-/opt/apps/yunxibakebot}"' in (
        deploy_server_source
    )
    assert "/opt/yunxibakebot" not in deploy_source
    assert "/opt/yunxibakebot" not in deploy_server_source
    assert "trap cleanup_temp_files EXIT" in deploy_source
