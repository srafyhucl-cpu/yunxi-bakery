from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_ledger_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "check_mistake_ledger.py"
    )
    spec = importlib.util.spec_from_file_location("check_mistake_ledger", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_empty_ledger_marker_passes(tmp_path: Path) -> None:
    ledger = load_ledger_module()
    ledger_file = tmp_path / "mistake-ledger.md"
    ledger_file.write_text("# Mistake Ledger\n\n暂无正式条目。\n", encoding="utf-8")

    result = ledger.check_ledger(ledger_file)

    assert result.passed is True
    assert result.entries == ()


def test_complete_entry_passes(tmp_path: Path) -> None:
    ledger = load_ledger_module()
    ledger_file = tmp_path / "mistake-ledger.md"
    ledger_file.write_text(
        "# Mistake Ledger\n\n"
        "## M-20260611-001：上线前未留证据\n\n"
        "- status: guarded\n"
        "- first_seen: 2026-06-11\n"
        "- severity: high\n"
        "- symptom: 上线前只有口头确认\n"
        "- root_cause: 缺少证据包规范\n"
        "- impact: 难以复盘\n"
        "- fix: 新增报告规范\n"
        "- new_guardrail: smoke JSON 留档\n"
        "- verification: python scripts/smoke_test.py --json\n"
        "- linked_trace: 20260611-harness\n"
        "- linked_files: docs/harness-engineering/core/verification-matrix.md\n"
        "- next_time_signal: 缺少报告会在收口检查中暴露\n",
        encoding="utf-8",
    )

    result = ledger.check_ledger(ledger_file)

    assert result.passed is True
    assert len(result.entries) == 1
    assert result.entries[0].entry_id == "M-20260611-001"


def test_missing_required_field_fails(tmp_path: Path) -> None:
    ledger = load_ledger_module()
    ledger_file = tmp_path / "mistake-ledger.md"
    ledger_file.write_text(
        "# Mistake Ledger\n\n"
        "## M-20260611-001：字段缺失\n\n"
        "- status: open\n"
        "- first_seen: 2026-06-11\n"
        "- severity: medium\n",
        encoding="utf-8",
    )

    result = ledger.check_ledger(ledger_file)

    assert result.passed is False
    assert any("missing field `symptom`" in issue for issue in result.issues)


def test_invalid_status_and_severity_fail(tmp_path: Path) -> None:
    ledger = load_ledger_module()
    ledger_file = tmp_path / "mistake-ledger.md"
    ledger_file.write_text(
        "# Mistake Ledger\n\n"
        "## M-20260611-001：枚举错误\n\n"
        "- status: done\n"
        "- first_seen: 2026-06-11\n"
        "- severity: urgent\n"
        "- symptom: 现象\n"
        "- root_cause: 根因\n"
        "- impact: 影响\n"
        "- fix: 修复\n"
        "- new_guardrail: 防线\n"
        "- verification: 验证\n"
        "- linked_trace: trace\n"
        "- linked_files: file\n"
        "- next_time_signal: signal\n",
        encoding="utf-8",
    )

    result = ledger.check_ledger(ledger_file)

    assert result.passed is False
    assert any("invalid status" in issue for issue in result.issues)
    assert any("invalid severity" in issue for issue in result.issues)
