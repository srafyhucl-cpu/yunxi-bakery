from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_snapshot_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "harness_snapshot.py"
    )
    spec = importlib.util.spec_from_file_location("harness_snapshot", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_git_status_groups_changed_files() -> None:
    snapshot = load_snapshot_module()

    status = snapshot.parse_git_status(
        " M README.md\n"
        "A  scripts/harness_snapshot.py\n"
        "?? docs/harness-engineering/\n"
        "R  old.md -> new.md\n"
    )

    assert status.modified_files == ("README.md", "scripts/harness_snapshot.py")
    assert status.untracked_files == ("docs/harness-engineering/",)
    assert status.other_files == ("R  old.md -> new.md",)
    assert status.has_changes is True


def test_read_latest_logbook_entry_reads_first_entry(tmp_path: Path) -> None:
    snapshot = load_snapshot_module()
    logbook = tmp_path / "LOGBOOK.md"
    logbook.write_text(
        "# Logbook\n\n"
        "## [2026-06-11] - docs(harness): 测试条目\n"
        "正文\n"
        "## [2026-06-10] - fix: 旧条目\n",
        encoding="utf-8",
    )

    latest_entry = snapshot.read_latest_logbook_entry(logbook)

    assert latest_entry == "[2026-06-11] - docs(harness): 测试条目"


def test_format_markdown_includes_trace_and_references() -> None:
    snapshot = load_snapshot_module()
    handoff = snapshot.HarnessSnapshot(
        trace_id="20260611-harness",
        goal="完善 Harness",
        generated_at="2026-06-11T00:00:00+00:00",
        current_status="in_progress",
        latest_logbook_entry="[2026-06-11] - docs(harness): 测试",
        git_status=snapshot.GitStatus(
            modified_files=("README.md",),
            untracked_files=("docs/harness-engineering/",),
            other_files=(),
        ),
        reference_entries=("AGENTS.md", "docs/harness-engineering/README.md"),
    )

    markdown = snapshot.format_markdown(handoff)

    assert "trace_id: 20260611-harness" in markdown
    assert "current_goal: 完善 Harness" in markdown
    assert "README.md" in markdown
    assert "docs/harness-engineering/README.md" in markdown


def test_write_output_refuses_to_overwrite(tmp_path: Path) -> None:
    snapshot = load_snapshot_module()
    output = tmp_path / "handoff.md"
    output.write_text("existing", encoding="utf-8")

    try:
        snapshot.write_output(output, "new")
    except FileExistsError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("应拒绝覆盖已有快照文件")


def test_write_output_uses_utf8_bom(tmp_path: Path) -> None:
    snapshot = load_snapshot_module()
    output = tmp_path / "handoff.md"

    snapshot.write_output(output, "内容")

    assert output.read_bytes().startswith(snapshot.UTF8_BOM)
    assert "内容" in output.read_text(encoding="utf-8-sig")
