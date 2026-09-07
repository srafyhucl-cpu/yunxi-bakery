import shutil
import subprocess
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT_DIR / "scripts" / "cleanup-local-artifacts.ps1"


def _script_text() -> str:
    return SCRIPT_PATH.read_bytes().decode("utf-8-sig")


def _decode_console_output(raw: bytes) -> str:
    """解码 PowerShell 控制台输出，UTF-8 优先，失败回退系统编码。"""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("mbcs", errors="replace")


def _run_powershell(argv: list[str], cwd: Path) -> "subprocess.CompletedProcess[str]":
    """执行清理脚本并按控制台实际编码解码输出。"""
    completed = subprocess.run(argv, cwd=cwd, capture_output=True, check=False)
    return subprocess.CompletedProcess(
        completed.args,
        completed.returncode,
        _decode_console_output(completed.stdout),
        _decode_console_output(completed.stderr),
    )


def test_cleanup_script_is_utf8_bom_for_windows_powershell_51() -> None:
    raw = SCRIPT_PATH.read_bytes()

    assert raw.startswith(b"\xef\xbb\xbf")


def test_cleanup_script_covers_project_level_caches_and_allows_scoped_recursive_cleanup() -> (
    None
):
    text = _script_text()

    assert 'Join-Path $workspacePath ".mypy_cache"' in text
    assert 'Join-Path $workspacePath ".pytest_cache"' in text
    assert 'Join-Path $workspacePath "node_modules"' in text
    assert 'Join-Path $workspacePath "miniapp\\miniprogram\\node_modules"' in text
    assert 'Join-Path $workspacePath ".venv"' in text
    assert "Remove-Item -LiteralPath $fileTarget -Force" in text
    assert "Remove-Item -LiteralPath $target -Recurse -Force" in text
    assert "Remove-Item -Path $NewRepoPath -Recurse" not in text
    assert "Assert-CustomTemporaryPath" in text
    assert "Assert-NotProtectedPath" in text
    assert '"D:\\Temp"' in text
    assert "[string[]]$TemporaryPath" in text
    assert "[switch]$OnlyTemporaryPath" in text
    assert "使用 -OnlyTemporaryPath 时必须至少提供一个" in text
    assert "预览授权令牌" in text
    assert "预览授权令牌不匹配" in text


@pytest.mark.skipif(
    shutil.which("powershell.exe") is None,
    reason="当前环境没有 Windows PowerShell 5.1",
)
def test_cleanup_script_parses_in_windows_powershell_51() -> None:
    completed = _run_powershell(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
        ],
        ROOT_DIR,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.skipif(
    shutil.which("powershell.exe") is None,
    reason="当前环境没有 Windows PowerShell 5.1",
)
def test_cleanup_script_recursively_removes_explicit_tmp_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / ".tmp-cleanup-test"
    nested = target / "nested"
    nested.mkdir(parents=True)
    (nested / "artifact.txt").write_text("rebuildable", encoding="utf-8")
    (workspace / "coverage.xml").write_text("keep", encoding="utf-8")
    duplicate_report = (
        workspace
        / "miniapp"
        / "reports"
        / "miniprogram-ci"
        / "miniprogram-ci-readiness-20260826-010232.json"
    )
    duplicate_report.parent.mkdir(parents=True)
    duplicate_report.write_text("keep", encoding="utf-8")

    preview = _run_powershell(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
            "-Workspace",
            str(workspace),
            "-TemporaryPath",
            ".tmp-cleanup-test",
            "-OnlyTemporaryPath",
        ],
        ROOT_DIR,
    )
    assert preview.returncode == 0, preview.stdout + preview.stderr
    assert target.exists()
    assert "递归批量清理" in preview.stdout
    preview_token = next(
        line.split(":", 1)[1].strip()
        for line in preview.stdout.splitlines()
        if line.startswith("预览授权令牌:")
    )

    executed = _run_powershell(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
            "-Workspace",
            str(workspace),
            "-TemporaryPath",
            ".tmp-cleanup-test",
            "-OnlyTemporaryPath",
            "-PreviewToken",
            preview_token,
            "-Execute",
        ],
        ROOT_DIR,
    )
    assert executed.returncode == 0, executed.stdout + executed.stderr
    assert not target.exists()
    assert (workspace / "coverage.xml").exists()
    assert duplicate_report.exists()


@pytest.mark.skipif(
    shutil.which("powershell.exe") is None,
    reason="当前环境没有 Windows PowerShell 5.1",
)
def test_cleanup_script_requires_preview_token(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / ".tmp-cleanup-test"
    target.mkdir(parents=True)
    (target / "artifact.txt").write_text("rebuildable", encoding="utf-8")

    completed = _run_powershell(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
            "-Workspace",
            str(workspace),
            "-TemporaryPath",
            ".tmp-cleanup-test",
            "-OnlyTemporaryPath",
            "-Execute",
        ],
        ROOT_DIR,
    )

    assert completed.returncode != 0
    assert "必须携带预览授权令牌" in completed.stderr
    assert target.exists()


@pytest.mark.skipif(
    shutil.which("powershell.exe") is None,
    reason="当前环境没有 Windows PowerShell 5.1",
)
def test_cleanup_script_rejects_unscoped_custom_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    unsafe = workspace / "not-a-temp-directory"
    unsafe.mkdir()

    completed = _run_powershell(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
            "-Workspace",
            str(workspace),
            "-TemporaryPath",
            "not-a-temp-directory",
        ],
        ROOT_DIR,
    )

    assert completed.returncode != 0
    assert "必须使用 .tmp- 或 pytest- 前缀" in completed.stderr


@pytest.mark.skipif(
    shutil.which("powershell.exe") is None,
    reason="当前环境没有 Windows PowerShell 5.1",
)
def test_cleanup_script_preserves_env_file_in_temporary_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / ".tmp-cleanup-test"
    target.mkdir(parents=True)
    secret = target / ".env.local"
    secret.write_text("DO_NOT_DELETE=1", encoding="utf-8")

    preview = _run_powershell(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
            "-Workspace",
            str(workspace),
            "-TemporaryPath",
            ".tmp-cleanup-test",
            "-OnlyTemporaryPath",
        ],
        ROOT_DIR,
    )
    assert preview.returncode == 0, preview.stdout + preview.stderr
    preview_token = next(
        line.split(":", 1)[1].strip()
        for line in preview.stdout.splitlines()
        if line.startswith("预览授权令牌:")
    )

    completed = _run_powershell(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
            "-Workspace",
            str(workspace),
            "-TemporaryPath",
            ".tmp-cleanup-test",
            "-OnlyTemporaryPath",
            "-PreviewToken",
            preview_token,
            "-Execute",
        ],
        ROOT_DIR,
    )

    assert completed.returncode != 0
    assert "拒绝处理环境文件" in completed.stderr
    assert secret.exists()
