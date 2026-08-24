from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from scripts import migrate_evidence_index_scope as mig


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True, text=True)


def _write_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "probe.py").write_text("probe", encoding="utf-8")
    index = repo / "evidence-index.md"
    index.write_text(
        "# Evidence Index\n\n"
        "## E-20260814-200：迁移测试\n\n"
        "- trace_id: test\n"
        "- generated_at: 2026-08-14\n"
        "- evidence_type: governance/migrate-test\n"
        "- file: `scripts/probe.py`；`reports/harness/x.json`\n"
        "- command: x\n"
        "- result: pass\n"
        "- related_logbook: x\n"
        "- related_adr: none\n"
        "- contains_sensitive_data: no\n"
        "- retention_note: x\n"
        "- summary: x\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "fixture")
    return repo


def _run(repo: Path, monkeypatch, *, dry_run: bool = False) -> int:
    monkeypatch.setattr(mig, "ROOT_DIR", repo)
    return mig.migrate(repo / "evidence-index.md", dry_run=dry_run)


def test_migrates_to_git_blob_model(tmp_path: Path, monkeypatch) -> None:
    repo = _write_fixture(tmp_path)
    assert _run(repo, monkeypatch) == 0
    text = (repo / "evidence-index.md").read_text(encoding="utf-8")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    assert f"`git:{head}:scripts/probe.py`" in text
    assert "`local:reports/harness/x.json`" in text
    assert f"- commit_sha: {head}" in text
    assert "- storage_scope: repository" in text
    digest = hashlib.sha256(b"probe").hexdigest()
    assert f"- sha256: {digest}" in text


def test_migration_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    repo = _write_fixture(tmp_path)
    _run(repo, monkeypatch)
    first = (repo / "evidence-index.md").read_text(encoding="utf-8")
    assert _run(repo, monkeypatch) == 0
    assert (repo / "evidence-index.md").read_text(encoding="utf-8") == first


def test_dry_run_does_not_write(tmp_path: Path, monkeypatch) -> None:
    repo = _write_fixture(tmp_path)
    before = (repo / "evidence-index.md").read_text(encoding="utf-8")
    assert _run(repo, monkeypatch, dry_run=True) == 0
    assert (repo / "evidence-index.md").read_text(encoding="utf-8") == before


def test_bom_heading_starts_new_entry(tmp_path: Path, monkeypatch) -> None:
    repo = _write_fixture(tmp_path)
    index = repo / "evidence-index.md"
    text = index.read_text(encoding="utf-8")
    index.write_text(
        text + "\n\ufeff## E-20260814-201：BOM 条目\n\n"
        "- trace_id: bom\n"
        "- generated_at: 2026-08-14\n"
        "- evidence_type: governance/bom-test\n"
        "- file: `scripts/probe.py`\n"
        "- command: x\n"
        "- result: pass\n"
        "- related_logbook: x\n"
        "- related_adr: none\n"
        "- contains_sensitive_data: no\n"
        "- retention_note: x\n"
        "- summary: x\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "bom entry")
    assert _run(repo, monkeypatch) == 0
    migrated = index.read_text(encoding="utf-8")
    assert "## E-20260814-201：BOM 条目" in migrated
    assert "- storage_scope: repository" in migrated
    assert "- commit_sha:" in migrated
