"""生产边界守卫测试：端口暴露、打包卫生、发布前置。"""

from pathlib import Path

import pytest
import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _compose() -> dict:
    """解析编排文件。"""
    with open(BACKEND_ROOT / "docker-compose.yml", encoding="utf-8") as file_obj:
        return yaml.safe_load(file_obj)


def test_production_ports_bound_to_loopback() -> None:
    """应用端口不得向所有网卡暴露，只允许回环或显式代理网络。"""
    services = _compose().get("services", {})
    assert services, "编排文件缺少服务定义"
    for name, service in services.items():
        for mapping in service.get("ports", []) or []:
            text = str(mapping)
            host_part = text.rsplit(":", 2)[0] if text.count(":") >= 2 else ""
            assert host_part in ("127.0.0.1", "localhost"), (
                f"服务 {name} 端口暴露越界: {text}"
            )
            assert not text.startswith("0.0.0.0"), f"服务 {name} 禁止全网卡绑定"


def test_env_files_never_baked_into_artifacts() -> None:
    """凭证文件不得进版本控制与镜像构建上下文。"""
    gitignore = (BACKEND_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore.splitlines()
    dockerignore = (BACKEND_ROOT / ".dockerignore").read_text(encoding="utf-8")
    lines = dockerignore.splitlines()
    assert ".env" in lines
    assert ".env.*" in lines


def test_compose_injects_env_at_runtime_only() -> None:
    """运行期注入凭证，不烘焙进镜像。"""
    services = _compose().get("services", {})
    app = services["app"]
    assert ".env" in list(app.get("env_file", []) or [])
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert ".env" not in dockerfile


def test_deploy_bundle_excludes_untracked_secrets(tmp_path: Path) -> None:
    """发布包只含已跟踪文件，未跟踪凭证不在包内。"""
    import subprocess

    bundle = tmp_path / "server.bundle"
    completed = subprocess.run(
        ["git", "bundle", "create", str(bundle), "HEAD"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip(f"当前环境无法创建 bundle: {completed.stderr[:200]}")
    verify = subprocess.run(
        ["git", "bundle", "list-heads", str(bundle)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert verify.returncode == 0
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ".env" not in tracked.stdout.splitlines()
    assert "backend/.env" not in tracked.stdout.splitlines()
