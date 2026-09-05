from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.harness_ci_summary import build_summary, main, render_markdown


def test_summary_fails_when_report_or_step_fails() -> None:
    summary = build_summary(
        {"status": "passed"},
        None,
        {"status": "passed"},
        {"contract_tests": "failure"},
        {"run_id": "run-1", "manifest_type": "harness_run"},
        {"status": "passed", "run_id": "run-1"},
    )
    assert summary["status"] == "failed"
    assert "harness_observation" in summary["failures"]
    assert "contract_tests" in summary["failures"]
    assert "失败" in render_markdown(summary)


def test_summary_passes_with_all_reports_and_steps_success() -> None:
    summary = build_summary(
        {"status": "passed"},
        {"status": "passed"},
        {"status": "passed"},
        {"contract_tests": "success"},
        {"run_id": "run-1", "manifest_type": "harness_run"},
        {"status": "passed", "run_id": "run-1"},
    )
    assert summary["status"] == "passed"


def test_missing_run_manifest_fails_summary() -> None:
    summary = build_summary(
        {"status": "passed"},
        {"status": "passed"},
        {"status": "passed"},
        None,
        None,
        {"status": "passed", "run_id": "run-1"},
    )
    assert summary["status"] == "failed"
    assert "run_manifest" in summary["failures"]
    assert summary["failure_classes"]["run_manifest"] == "report_missing"


def test_invalid_run_manifest_fails_summary() -> None:
    summary = build_summary(
        {"status": "passed"},
        {"status": "passed"},
        {"status": "passed"},
        None,
        {"run_id": "run-1"},
        {"status": "passed", "run_id": "run-1"},
    )
    assert summary["status"] == "failed"
    assert "run_manifest" in summary["failures"]


def test_missing_artifact_index_fails_summary() -> None:
    summary = build_summary(
        {"status": "passed"},
        {"status": "passed"},
        {"status": "passed"},
        None,
        {"run_id": "run-1", "manifest_type": "harness_run"},
        None,
    )
    assert summary["status"] == "failed"
    assert "artifact_index" in summary["failures"]
    assert summary["failure_classes"]["artifact_index"] == "report_missing"


def test_failed_artifact_index_fails_summary() -> None:
    summary = build_summary(
        {"status": "passed"},
        {"status": "passed"},
        {"status": "passed"},
        None,
        {"run_id": "run-1", "manifest_type": "harness_run"},
        {"status": "failed", "run_id": "run-1", "missing_files": ["doc-garden-*.json"]},
    )
    assert summary["status"] == "failed"
    assert "artifact_index" in summary["failures"]
    assert summary["failure_classes"]["artifact_index"] == "index_failed"


def test_markdown_contains_chinese_failure_sections() -> None:
    summary = build_summary(
        None,
        None,
        None,
        {"doc_garden": "failure"},
        None,
        None,
    )
    markdown = render_markdown(summary)
    assert "失败分类" in markdown
    assert "证据路径" in markdown
    assert "未验证范围" in markdown
    assert "report_missing" in markdown
    assert "step_failed" in markdown
    assert "backend/reports/harness/ci-quality-loop.run.json" in markdown


def test_main_exit_codes_and_double_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    manifest_path = tmp_path / "run.json"
    manifest_path.write_text(
        json.dumps({"run_id": "run-1", "manifest_type": "harness_run"}),
        encoding="utf-8",
    )
    index_path = tmp_path / "index.json"
    index_path.write_text(
        json.dumps({"status": "passed", "run_id": "run-1"}), encoding="utf-8"
    )
    summary_out = tmp_path / "ci-summary.md"
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    exit_code = main(
        [
            "--eval-report",
            str(eval_path),
            "--run-manifest",
            str(manifest_path),
            "--artifact-index",
            str(index_path),
            "--summary-output",
            str(summary_out),
        ]
    )
    # 缺 observation / doc garden 报告，应显式失败。
    assert exit_code == 1
    written = summary_out.read_text(encoding="utf-8")
    assert "状态：**failed**" in written

    observation_path = tmp_path / "observation.json"
    observation_path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    garden_path = tmp_path / "garden.json"
    garden_path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    summary_out_second = tmp_path / "ci-summary-second.md"
    exit_code = main(
        [
            "--eval-report",
            str(eval_path),
            "--observation-report",
            str(observation_path),
            "--doc-garden-report",
            str(garden_path),
            "--run-manifest",
            str(manifest_path),
            "--artifact-index",
            str(index_path),
            "--summary-output",
            str(summary_out_second),
        ]
    )
    assert exit_code == 0
    assert "状态：**passed**" in summary_out_second.read_text(encoding="utf-8")


def test_summary_output_refuses_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary_out = tmp_path / "ci-summary.md"
    summary_out.write_text("旧证据", encoding="utf-8")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    with pytest.raises(FileExistsError):
        main(["--summary-output", str(summary_out)])
    assert summary_out.read_text(encoding="utf-8") == "旧证据"
