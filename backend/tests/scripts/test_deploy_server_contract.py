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
    assert 'READY_URL="http://127.0.0.1:7001/ready"' in source
    assert "ready_status=$(curl" in source


def test_bundle_deployment_targets_current_application_root() -> None:
    root = Path(__file__).resolve().parents[2]
    deploy_source = (root / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    deploy_server_source = (root / "scripts" / "deploy_server.sh").read_text(
        encoding="utf-8"
    )

    assert 'REMOTE_DIR="/opt/apps/yunxibakebot"' in deploy_source
    assert 'PROJECT_DIR="/opt/apps/yunxibakebot"' in deploy_server_source
    assert "/opt/yunxibakebot" not in deploy_source
    assert "/opt/yunxibakebot" not in deploy_server_source
