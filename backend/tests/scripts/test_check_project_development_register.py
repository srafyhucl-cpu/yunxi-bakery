from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from pathlib import Path


def load_register_module():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_project_development_register.py"
    )
    spec = importlib.util.spec_from_file_location(
        "check_project_development_register", script_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_current_project_register_passes() -> None:
    module = load_register_module()
    result = module.check_project_development_register()
    assert result.passed, result.issues
    assert len(result.task_statuses) >= 10


def test_duplicate_task_id_is_rejected(tmp_path: Path) -> None:
    module = load_register_module()
    state = tmp_path / "PROJECT-STATE.md"
    original = Path(__file__).resolve().parents[3] / "PROJECT-STATE.md"
    content = original.read_text(encoding="utf-8")
    duplicate = (
        "| T-P0-MONOREPO | 重复任务 | completed | P0 | 项目负责人 | main | "
        "1c2a3ea | — | test | 保持基线 |"
    )
    content = re.sub(
        r"(?m)^(\| T-P0-MONOREPO \|.*)$",
        r"\1\n" + duplicate,
        content,
        count=1,
    )
    state.write_text(content, encoding="utf-8")
    result = module.parse_register(state)
    assert not result.passed
    assert any("task_id 重复" in issue for issue in result.issues)


def test_invalid_status_is_rejected(tmp_path: Path) -> None:
    module = load_register_module()
    state = tmp_path / "PROJECT-STATE.md"
    original = Path(__file__).resolve().parents[3] / "PROJECT-STATE.md"
    content = original.read_text(encoding="utf-8").replace(
        "| T-P2-PREP | P2 试运行准备段 | completed |",
        "| T-P2-PREP | P2 试运行准备段 | executing |",
        1,
    )
    state.write_text(content, encoding="utf-8")
    result = module.parse_register(state)
    assert not result.passed
    assert any("非法 status" in issue for issue in result.issues)


def test_view_status_conflict_is_rejected(tmp_path: Path) -> None:
    module = load_register_module()
    state = tmp_path / "PROJECT-STATE.md"
    original = Path(__file__).resolve().parents[3] / "PROJECT-STATE.md"
    content = original.read_text(encoding="utf-8").replace(
        "| T-P2-PREP | P2 试运行准备段 | completed |",
        "| T-P2-PREP | P2 试运行准备段 | active |",
        1,
    )
    state.write_text(content, encoding="utf-8")
    result = module.parse_register(state)
    assert not result.passed
    assert any("状态视图 completed" in issue for issue in result.issues)


def test_task_metadata_requires_branch_and_matches_register(tmp_path: Path) -> None:
    module = load_register_module()
    source_dir = Path(__file__).resolve().parents[3] / "docs" / "tasks"
    tasks_dir = tmp_path / "tasks"
    shutil.copytree(source_dir, tasks_dir)
    task = next(tasks_dir.glob("20260829-P0-1-*.md"))
    content = task.read_text(encoding="utf-8").replace("> branch: main\n", "", 1)
    task.write_text(content, encoding="utf-8")
    result = module.check_project_development_register(tasks_dir=tasks_dir)
    assert not result.passed
    assert any("缺少元数据 branch" in issue for issue in result.issues)


def test_nonexistent_branch_is_rejected(tmp_path: Path) -> None:
    module = load_register_module()
    original = Path(__file__).resolve().parents[3] / "PROJECT-STATE.md"
    state = tmp_path / "PROJECT-STATE.md"
    content = original.read_text(encoding="utf-8").replace(
        "| main | 本仓 Git 分支 | 当前 |",
        "| codex/not-created | 本仓 Git 分支 | 候选 |",
        1,
    )
    state.write_text(content, encoding="utf-8")
    result = module.parse_register(state)
    assert not result.passed
    assert any("不存在的本地分支" in issue for issue in result.issues)


def test_unknown_view_task_id_reports_failure_without_exception(tmp_path: Path) -> None:
    module = load_register_module()
    original = Path(__file__).resolve().parents[3] / "PROJECT-STATE.md"
    state = tmp_path / "PROJECT-STATE.md"
    content = original.read_text(encoding="utf-8").replace(
        "`T-P0-MONOREPO`、`T-P05-ASSET-MIGRATION`、`T-P2-PREP`、`T-HARNESS-REGISTER`",
        "`T-P0-MONOREPO`、`T-P05-ASSET-MIGRATION`、`T-P2-PREP`、`T-NOT-REGISTERED`",
        1,
    )
    state.write_text(content, encoding="utf-8")
    result = module.parse_register(state)
    assert not result.passed
    assert any("引用不存在的 task_id" in issue for issue in result.issues)


def test_task_branch_must_match_register(tmp_path: Path) -> None:
    module = load_register_module()
    original = Path(__file__).resolve().parents[3] / "PROJECT-STATE.md"
    state = tmp_path / "PROJECT-STATE.md"
    tasks_dir = tmp_path / "tasks"
    source_dir = Path(__file__).resolve().parents[3] / "docs" / "tasks"
    shutil.copytree(source_dir, tasks_dir)
    task = next(tasks_dir.glob("20260829-P0-1-*.md"))
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "> branch: main", "> branch: codex/other", 1
        ),
        encoding="utf-8",
    )
    state.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
    result = module.check_project_development_register(state, tasks_dir)
    assert not result.passed
    assert any("branch 与总表不一致" in issue for issue in result.issues)


def test_workspace_state_must_match_git_status(tmp_path: Path) -> None:
    module = load_register_module()
    original = Path(__file__).resolve().parents[3] / "PROJECT-STATE.md"
    state = tmp_path / "PROJECT-STATE.md"
    content = original.read_text(encoding="utf-8").replace(
        "workspace_state: dirty", "workspace_state: clean", 1
    )
    state.write_text(content, encoding="utf-8")
    result = module.parse_register(state)
    assert not result.passed
    assert any("workspace_state 与 Git 不一致" in issue for issue in result.issues)
