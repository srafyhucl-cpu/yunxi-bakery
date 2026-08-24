from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from scripts import verify_secrets_baseline as vsb


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True, text=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / ".secrets.baseline").write_text("{}", encoding="utf-8")
    _git(repo, "add", ".secrets.baseline")
    _git(repo, "commit", "-m", "init")
    return repo


def _run(repo: Path, monkeypatch) -> int:
    monkeypatch.setattr(vsb, "ROOT_DIR", repo)
    monkeypatch.setattr(
        vsb,
        "CHANGES_LOG",
        repo / "docs" / "harness-engineering" / "core" / "secrets-baseline-changes.md",
    )
    return vsb.main()


def _record_text(
    old_sha: str,
    new_sha: str,
    *,
    missing: tuple[str, ...] = (),
) -> str:
    fields = {
        "old_sha256": old_sha,
        "new_sha256": new_sha,
        "command": "detect-secrets scan --all-files",
        "version": "detect-secrets 1.5.0",
        "trace_id": "test-trace",
        "approved_by": "project owner",
    }
    lines = ["## [2026-08-14] - secrets baseline 受控更新"]
    for key, value in fields.items():
        if key in missing:
            continue
        lines.append(f"- {key}: {value}")
    lines.append("")
    return "\n".join(lines)


def _write_record(
    repo: Path,
    old_sha: str,
    new_sha: str,
    *,
    missing: tuple[str, ...] = (),
) -> Path:
    log = repo / "docs" / "harness-engineering" / "core" / "secrets-baseline-changes.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(_record_text(old_sha, new_sha, missing=missing), encoding="utf-8")
    return log


def test_clean_worktree_passes(tmp_path: Path, monkeypatch) -> None:
    repo = _init_repo(tmp_path)
    assert _run(repo, monkeypatch) == 0


def test_worktree_pollution_fails(tmp_path: Path, monkeypatch) -> None:
    repo = _init_repo(tmp_path)
    (repo / ".secrets.baseline").write_text("{}polluted", encoding="utf-8")
    assert _run(repo, monkeypatch) == 1


def test_staged_change_without_record_fails(tmp_path: Path, monkeypatch) -> None:
    repo = _init_repo(tmp_path)
    (repo / ".secrets.baseline").write_text("{staged}", encoding="utf-8")
    _git(repo, "add", ".secrets.baseline")
    assert _run(repo, monkeypatch) == 1


def test_staged_change_with_approved_record_passes(tmp_path: Path, monkeypatch) -> None:
    repo = _init_repo(tmp_path)
    old_sha = hashlib.sha256(b"{}").hexdigest()
    (repo / ".secrets.baseline").write_text("{staged}", encoding="utf-8")
    _git(repo, "add", ".secrets.baseline")
    new_sha = hashlib.sha256(b"{staged}").hexdigest()
    log = _write_record(repo, old_sha, new_sha)
    _git(repo, "add", str(log.relative_to(repo)))
    assert _run(repo, monkeypatch) == 0


def test_missing_record_file_with_clean_worktree_passes(
    tmp_path: Path, monkeypatch
) -> None:
    repo = _init_repo(tmp_path)
    assert _run(repo, monkeypatch) == 0


def test_unstaged_record_file_fails(tmp_path: Path, monkeypatch) -> None:
    """记录文件只在工作区修改、未 git add 时，即使哈希对匹配也必须阻断。"""
    repo = _init_repo(tmp_path)
    old_sha = hashlib.sha256(b"{}").hexdigest()
    (repo / ".secrets.baseline").write_text("{staged}", encoding="utf-8")
    _git(repo, "add", ".secrets.baseline")
    new_sha = hashlib.sha256(b"{staged}").hexdigest()
    _write_record(repo, old_sha, new_sha)
    assert _run(repo, monkeypatch) == 1


def test_missing_record_fields_fails(tmp_path: Path, monkeypatch) -> None:
    """记录字段缺失（如无 approved_by / trace_id）时，即使哈希对匹配也必须阻断。"""
    repo = _init_repo(tmp_path)
    old_sha = hashlib.sha256(b"{}").hexdigest()
    (repo / ".secrets.baseline").write_text("{staged}", encoding="utf-8")
    _git(repo, "add", ".secrets.baseline")
    new_sha = hashlib.sha256(b"{staged}").hexdigest()
    log = _write_record(repo, old_sha, new_sha, missing=("approved_by", "trace_id"))
    _git(repo, "add", str(log.relative_to(repo)))
    assert _run(repo, monkeypatch) == 1


def test_historical_record_reuse_fails(tmp_path: Path, monkeypatch) -> None:
    """已提交过的历史记录不得复用作本次变更的批准。"""
    repo = _init_repo(tmp_path)
    old_sha = hashlib.sha256(b"{}").hexdigest()
    new_sha = hashlib.sha256(b"{staged}").hexdigest()
    log = _write_record(repo, old_sha, new_sha)
    _git(repo, "add", str(log.relative_to(repo)))
    _git(repo, "commit", "-m", "record history")

    (repo / ".secrets.baseline").write_text("{staged}", encoding="utf-8")
    _git(repo, "add", ".secrets.baseline")
    log.write_text(
        _record_text(old_sha, new_sha) + "- note: 再次触发变更\n",
        encoding="utf-8",
    )
    _git(repo, "add", str(log.relative_to(repo)))
    assert _run(repo, monkeypatch) == 1


def test_git_failure_fails(tmp_path: Path, monkeypatch) -> None:
    """git 不可用 / 目录非 git 仓库时按阻断处理，不允许静默通过。"""
    norepo = tmp_path / "norepo"
    norepo.mkdir()
    assert _run(norepo, monkeypatch) == 1


def test_git_diff_128_raises(tmp_path: Path, monkeypatch) -> None:
    """git diff 返回 128（非仓库 / 异常）必须抛 _GitFailure，不允许当作"无差异"。"""
    norepo = tmp_path / "norepo"
    norepo.mkdir()
    monkeypatch.setattr(vsb, "ROOT_DIR", norepo)
    with pytest.raises(vsb._GitFailure):
        vsb._git_has_unstaged(vsb.BASELINE_REL)
    with pytest.raises(vsb._GitFailure):
        vsb._git_has_staged(vsb.BASELINE_REL)
