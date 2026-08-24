"""部署和容器脚本的删除边界合同测试。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_RECURSIVE_CLEANUP = ("rm -rf", "find . -type d", "find . -type f", "truncate")


def test_deployment_script_does_not_batch_delete_workspace_content() -> None:
    deploy_script = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")

    assert not any(pattern in deploy_script for pattern in FORBIDDEN_RECURSIVE_CLEANUP)


def test_dockerfile_does_not_use_recursive_cleanup() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "rm -rf" not in dockerfile
    assert "AS dependency-installer" in dockerfile
    assert "COPY --from=dependency-installer" in dockerfile
