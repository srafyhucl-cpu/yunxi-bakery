"""Harness P0 中文治理检查合同测试。"""

from __future__ import annotations

from pathlib import Path

from scripts import check_chinese_governance


def test_current_chinese_governance_passes() -> None:
    report = check_chinese_governance.build_report()

    assert report["status"] == "passed", report["issues"]
    assert report["coverage"]["ratio"] == 1.0


def test_bare_machine_status_is_rejected(tmp_path: Path) -> None:
    state = tmp_path / "PROJECT-STATE.md"
    state.write_text("当前任务 blocked，等待批准。\n", encoding="utf-8")

    result = check_chinese_governance.check_project_state_no_bare_status(tmp_path)

    assert not result.passed
    assert any("缺少中文标签" in detail for detail in result.details)


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
