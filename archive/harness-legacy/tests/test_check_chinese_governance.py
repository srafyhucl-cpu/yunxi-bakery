"""Harness P0 中文治理检查合同测试。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import check_chinese_governance


def test_current_chinese_governance_passes() -> None:
    report = check_chinese_governance.build_report()

    assert report["status"] == "passed", report["issues"]
    assert report["coverage"]["ratio"] == 1.0
    assert report["coverage"]["dimension_ratio"] == 1.0


def _write_governance_model(root: Path, dimension: dict[str, object]) -> None:
    path = root / "docs" / "harness-engineering" / "core" / "chinese-governance.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "model_id": "yunxi-chinese-governance",
                "dimensions": [dimension],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_governance_model_missing_dimension_is_rejected(tmp_path: Path) -> None:
    _write_governance_model(
        tmp_path,
        {
            "id": "documentation",
            "name": "文档",
            "priority": "P0",
            "required_files": [],
            "required_markers": [],
        },
    )

    result = check_chinese_governance.check_governance_model(tmp_path)

    assert not result.passed
    assert any("六维 ID" in detail for detail in result.details)


def test_governance_model_priority_drift_is_rejected(tmp_path: Path) -> None:
    _write_governance_model(
        tmp_path,
        {
            "id": "documentation",
            "name": "文档",
            "priority": "P1",
            "required_files": [],
            "required_markers": ["中文"],
        },
    )

    result = check_chinese_governance.check_governance_model(tmp_path)

    assert not result.passed
    assert any("priority 应为 P0" in detail for detail in result.details)


def test_collaboration_template_missing_marker_is_rejected(tmp_path: Path) -> None:
    _write_governance_model(
        tmp_path,
        {
            "id": "collaboration",
            "name": "协作沟通",
            "priority": "P0",
            "required_files": ["collaboration.md"],
            "required_markers": ["trace_id", "验证"],
        },
    )
    (tmp_path / "collaboration.md").write_text("trace_id\n", encoding="utf-8")

    result = check_chinese_governance.check_collaboration_contract(tmp_path)

    assert not result.passed
    assert any("缺少治理标识 验证" in detail for detail in result.details)


def test_collaboration_markers_are_enforced_per_file(tmp_path: Path) -> None:
    _write_governance_model(
        tmp_path,
        {
            "id": "collaboration",
            "name": "协作沟通",
            "priority": "P0",
            "required_files": ["issue.md", "pull-request.md"],
            "required_markers": ["trace_id", "验证"],
            "file_markers": {
                "issue.md": ["trace_id", "验证"],
                "pull-request.md": ["trace_id", "验证"],
            },
        },
    )
    (tmp_path / "issue.md").write_text("中文 trace_id\n", encoding="utf-8")
    (tmp_path / "pull-request.md").write_text("中文 验证\n", encoding="utf-8")

    result = check_chinese_governance.check_collaboration_contract(tmp_path)

    assert not result.passed
    assert any("缺少逐文件标识" in detail for detail in result.details)


def test_english_interface_copy_is_rejected(tmp_path: Path) -> None:
    _write_governance_model(
        tmp_path,
        {
            "id": "interface",
            "name": "系统界面",
            "priority": "P0",
            "targets": [{"path": "ui", "extensions": [".wxml"]}],
            "required_markers": ["错误", "加载"],
        },
    )
    ui_path = tmp_path / "ui" / "index.wxml"
    ui_path.parent.mkdir(parents=True, exist_ok=True)
    ui_path.write_text("<view>English button</view>\n错误 加载\n", encoding="utf-8")

    result = check_chinese_governance.check_interface_copy(tmp_path)

    assert not result.passed
    assert any("用户可见英文文案未中文化" in detail for detail in result.details)


def test_single_and_mixed_english_interface_copy_is_rejected() -> None:
    assert check_chinese_governance._has_untranslated_ui_text("Submit")
    assert check_chinese_governance._has_untranslated_ui_text("加载 Loading")
    assert check_chinese_governance._has_untranslated_ui_text("local 发券")
    assert not check_chinese_governance._has_untranslated_ui_text(
        "搜索 msg_id、Webhook 或错误信息"
    )


def test_missing_interface_target_is_rejected(tmp_path: Path) -> None:
    _write_governance_model(
        tmp_path,
        {
            "id": "interface",
            "name": "系统界面",
            "priority": "P0",
            "targets": [{"path": "missing-ui", "extensions": [".wxml"]}],
            "required_markers": ["错误", "加载"],
        },
    )

    result = check_chinese_governance.check_interface_copy(tmp_path)

    assert not result.passed
    assert any("target 路径不存在" in detail for detail in result.details)


def test_english_natural_language_comment_is_rejected(tmp_path: Path) -> None:
    _write_governance_model(
        tmp_path,
        {
            "id": "code_comments",
            "name": "代码注释",
            "priority": "P1",
            "targets": [{"path": "src", "extensions": [".py"]}],
            "required_markers": ["中文注释"],
        },
    )
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "# English natural language comment\nvalue = 1\n", encoding="utf-8"
    )

    result = check_chinese_governance.check_code_comments(tmp_path)

    assert not result.passed
    assert any("自然语言注释应使用中文" in detail for detail in result.details)


def test_non_python_comment_parser_respects_strings_and_directives(
    tmp_path: Path,
) -> None:
    template_quote = chr(96)
    source = tmp_path / "example.ts"
    source.write_text(
        'const endpoint = "https://example.com/api";\n'
        'const marker = "// not a comment";\n'
        '/// <reference path="./types.d.ts" />\n'
        + f"const template = {template_quote}first line\n"
        + f"// still inside template{template_quote};\n"
        + "value();//Fetch data from https://example.com/api\n"
        + "/* Multi-line English\n"
        + " * comment body */\n",
        encoding="utf-8",
    )

    comments = check_chinese_governance._natural_language_comments(source)
    bodies = [body for _, body in comments]

    assert len(comments) == 2
    assert any(body.startswith("Fetch data from") for body in bodies)
    assert any("Multi-line English" in body for body in bodies)
    assert all("not a comment" not in body for body in bodies)
    assert all("still inside template" not in body for body in bodies)


def test_bare_machine_status_is_rejected(tmp_path: Path) -> None:
    state = tmp_path / "PROJECT-STATE.md"
    state.write_text("当前任务 blocked，等待批准。\n", encoding="utf-8")

    result = check_chinese_governance.check_project_state_no_bare_status(tmp_path)

    assert not result.passed
    assert any("缺少中文标签" in detail for detail in result.details)


def test_unrelated_parentheses_do_not_hide_bare_machine_status(tmp_path: Path) -> None:
    state = tmp_path / "PROJECT-STATE.md"
    state.write_text("当前任务 blocked（等待批准）。\n", encoding="utf-8")

    result = check_chinese_governance.check_project_state_no_bare_status(tmp_path)

    assert not result.passed
    assert any("缺少中文标签" in detail for detail in result.details)


def test_unknown_task_status_is_rejected(tmp_path: Path) -> None:
    task = tmp_path / "docs" / "tasks" / "example.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text(
        "# 示例任务\n\n> status: finished\n> status_label: 已完成（finished）\n",
        encoding="utf-8",
    )

    result = check_chinese_governance.check_task_status_labels(tmp_path)

    assert not result.passed
    assert any("未知机器状态 finished" in detail for detail in result.details)


def test_governance_file_without_chinese_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("Only English", encoding="utf-8")

    result = check_chinese_governance.check_governance_file_coverage(tmp_path)

    assert not result.passed
    assert any("缺少中文" in detail for detail in result.details)


def test_high_risk_path_requires_semantic_markers(tmp_path: Path) -> None:
    for relative in check_chinese_governance.HIGH_RISK_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 中文注释\n", encoding="utf-8")

    result = check_chinese_governance.check_high_risk_path_readability(tmp_path)

    assert not result.passed
    assert any("语义断言缺失" in detail for detail in result.details)


def test_high_risk_python_ignores_comment_only_markers(tmp_path: Path) -> None:
    for relative in check_chinese_governance.HIGH_RISK_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        required = " ".join(check_chinese_governance.HIGH_RISK_REQUIRED_TEXT[relative])
        if path.suffix == ".py":
            path.write_text(
                f"# {required}\nimport argparse\n"
                "argparse.ArgumentParser(description='English only')\n",
                encoding="utf-8",
            )
        else:
            path.write_text(required, encoding="utf-8")

    result = check_chinese_governance.check_high_risk_path_readability(tmp_path)

    assert not result.passed
    assert any(
        "backend/scripts/preflight_production.py: 高风险语义断言缺失" in detail
        for detail in result.details
    )
