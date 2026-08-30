import shutil
import subprocess
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT_DIR / "scripts" / "cleanup-local-artifacts.ps1"


def _script_text() -> str:
    return SCRIPT_PATH.read_bytes().decode("utf-8-sig")


def test_cleanup_script_is_utf8_bom_for_windows_powershell_51() -> None:
    raw = SCRIPT_PATH.read_bytes()

    assert raw.startswith(b"\xef\xbb\xbf")


def test_cleanup_script_covers_project_level_caches_and_deletes_files_only() -> None:
    text = _script_text()

    assert 'Join-Path $workspacePath ".mypy_cache"' in text
    assert 'Join-Path $workspacePath ".pytest_cache"' in text
    assert 'Join-Path $workspacePath "node_modules"' in text
    assert 'Join-Path $workspacePath "miniapp\\miniprogram\\node_modules"' in text
    assert 'Join-Path $workspacePath ".venv"' in text
    assert "Remove-Item -LiteralPath $file.FullName -Force" in text
    assert "Remove-Item -LiteralPath $fileTarget -Force" in text
    assert "Remove-Item -Recurse" not in text
    assert "Remove-Item -Path $NewRepoPath -Recurse" not in text


@pytest.mark.skipif(
    shutil.which("powershell.exe") is None,
    reason="当前环境没有 Windows PowerShell 5.1",
)
def test_cleanup_script_parses_in_windows_powershell_51() -> None:
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
