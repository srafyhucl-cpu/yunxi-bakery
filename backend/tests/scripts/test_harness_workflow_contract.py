"""Harness P1/P2 workflow YAML 合同测试。

验证 workflow 可被 YAML 解析、artifact 上传步骤结构完整、
质量步骤允许保留报告但最终汇总必须失败。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[3] / ".github" / "workflows" / "harness-p1-p2.yml"
)
P0_WORKFLOW_PATH = (
    Path(__file__).resolve().parents[3] / ".github" / "workflows" / "harness-p0.yml"
)


def _load_workflow(path: Path = WORKFLOW_PATH) -> dict:
    text = path.read_text(encoding="utf-8")
    payload = yaml.safe_load(text)
    assert isinstance(payload, dict), "workflow 根节点必须是对象"
    assert "jobs" in payload, "workflow 缺少 jobs"
    return payload


def _get_job(payload: dict) -> dict:
    jobs = payload["jobs"]
    assert isinstance(jobs, dict) and jobs, "workflow 必须至少包含一个 job"
    job_name = next(iter(jobs))
    job = jobs[job_name]
    assert isinstance(job, dict), "job 必须是对象"
    return job


def _get_steps(job: dict) -> list[dict]:
    steps = job.get("steps")
    assert isinstance(steps, list) and steps, "job 必须包含 steps"
    return steps


def _find_step(steps: list[dict], *, uses_contains: str) -> dict:
    for step in steps:
        if uses_contains in str(step.get("uses", "")):
            return step
    raise AssertionError(f"workflow 缺少 uses 包含 {uses_contains} 的步骤")


def test_workflow_yaml_is_parseable() -> None:
    payload = _load_workflow()
    job = _get_job(payload)
    assert isinstance(job.get("runs-on"), str)
    assert _get_steps(job)


def test_checkout_keeps_full_git_history() -> None:
    payload = _load_workflow()
    steps = _get_steps(_get_job(payload))
    checkout = _find_step(steps, uses_contains="actions/checkout")
    with_block = checkout.get("with")
    assert isinstance(with_block, dict), "checkout 步骤必须包含 with"
    assert with_block.get("fetch-depth") == 0, "checkout 必须保留 fetch-depth: 0"


def test_upload_artifact_step_structure() -> None:
    payload = _load_workflow()
    steps = _get_steps(_get_job(payload))
    upload = _find_step(steps, uses_contains="actions/upload-artifact")
    # if、uses、with 必须位于同一个 step 映射层级。
    assert "if" in upload, "上传步骤缺少 if"
    assert "uses" in upload, "上传步骤缺少 uses"
    assert "with" in upload, "上传步骤缺少 with"
    assert upload["if"] == "always()", "上传步骤必须使用 if: always()"
    with_block = upload["with"]
    assert isinstance(with_block, dict), "上传步骤 with 必须是对象"
    assert with_block.get("if-no-files-found") == "error", (
        "上传步骤必须使用 if-no-files-found: error，缺失报告时显式失败"
    )
    assert with_block.get("path") == "backend/reports/harness/**", (
        "上传路径必须覆盖全部 JSON 报告、manifest、候选文件和 summary"
    )


def test_summary_step_must_fail_job_and_not_swallow_errors() -> None:
    payload = _load_workflow()
    steps = _get_steps(_get_job(payload))
    summary_steps = [
        step for step in steps if "harness_ci_summary.py" in str(step.get("run", ""))
    ]
    assert summary_steps, "workflow 缺少 Harness 汇总步骤"
    summary = summary_steps[-1]
    assert summary.get("if") == "always()", "汇总步骤必须使用 if: always()"
    assert summary.get("continue-on-error") is not True, (
        "最终汇总步骤不得使用 continue-on-error，必须继承失败退出码"
    )
    upload = _find_step(steps, uses_contains="actions/upload-artifact")
    # 汇总步骤与上传步骤都必须无条件执行，保证失败时仍保留证据。
    assert upload.get("if") == "always()"


def test_quality_steps_keep_reports_but_artifact_always_uploads() -> None:
    payload = _load_workflow()
    steps = _get_steps(_get_job(payload))
    quality_steps = [
        step
        for step in steps
        if step.get("continue-on-error") is True and step.get("run")
    ]
    assert quality_steps, "质量步骤应通过 continue-on-error 保留后续报告"
    upload = _find_step(steps, uses_contains="actions/upload-artifact")
    assert upload.get("if") == "always()", "失败路径仍必须上传 artifact"


@pytest.mark.parametrize("workflow_path", [WORKFLOW_PATH, P0_WORKFLOW_PATH])
def test_ci_runtime_directories_stay_outside_workspace(workflow_path: Path) -> None:
    _load_workflow(workflow_path)
    workflow_text = workflow_path.read_text(encoding="utf-8")
    assert "$env:RUNNER_TEMP" in workflow_text
    assert "$env:GITHUB_ENV" in workflow_text
    assert "${{ github.workspace }}" not in workflow_text


def test_p0_dependency_report_is_staged_after_gate() -> None:
    payload = _load_workflow(P0_WORKFLOW_PATH)
    steps = _get_steps(_get_job(payload))
    alignment = next(
        step
        for step in steps
        if "check_requirements_lock_alignment.py" in str(step.get("run", ""))
    )
    alignment_run = str(alignment["run"])
    assert "RUNNER_TEMP" in alignment_run
    assert "reports/harness/requirements-lock-alignment.json" not in alignment_run

    gate_index = next(
        index
        for index, step in enumerate(steps)
        if "harness_p0_gate.py" in str(step.get("run", ""))
    )
    stage_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Stage dependency lock report"
    )
    assert stage_index > gate_index
    assert "requirements-lock-alignment.json" in str(steps[stage_index].get("run", ""))


def test_failure_candidate_generation_step_contract() -> None:
    payload = _load_workflow()
    steps = _get_steps(_get_job(payload))
    candidate_steps = [
        step
        for step in steps
        if "harness_failure_candidate.py" in str(step.get("run", ""))
    ]
    assert candidate_steps, "workflow 缺少错误候选生成步骤"
    candidate = candidate_steps[0]
    assert candidate.get("if") == "always()", "候选生成必须在 if: always() 阶段执行"
    assert candidate.get("continue-on-error") is True, (
        "候选生成失败不得覆盖原始 CI 失败，由汇总标记 failure_candidate_generation"
    )
    run_script = str(candidate.get("run", ""))
    assert "--from-ci" in run_script
    assert "--ledger ERRORS.md" in run_script, "候选生成必须查重 ERRORS.md"
    assert "--candidate-dir backend/reports/harness/failure-candidates" in run_script

    # 候选生成必须先于 artifact index，保证候选目录纳入索引。
    index_steps = [
        index
        for index, step in enumerate(steps)
        if "build_harness_artifact_index.py" in str(step.get("run", ""))
    ]
    assert index_steps, "workflow 缺少 artifact index 步骤"
    candidate_index = steps.index(candidate)
    assert candidate_index < index_steps[0], "候选生成必须先于 artifact index"

    summary_steps = [
        step for step in steps if "harness_ci_summary.py" in str(step.get("run", ""))
    ]
    assert summary_steps, "workflow 缺少汇总步骤"
    summary_run = str(summary_steps[-1].get("run", ""))
    assert "--candidates-report" in summary_run, "汇总必须读取候选生成报告"
    assert "failure_candidate_generation=" in summary_run, (
        "汇总必须标记 failure_candidate_generation 步骤结果"
    )
    assert "--summary-output" in summary_run, "汇总必须双写 ci-summary 证据文件"

    # 最终 artifact index 必须在汇总（含 ci-summary md 写出）之后，使索引
    # 覆盖并哈希校验最终 Summary；该步骤不得 continue-on-error。
    final_index_steps = [
        step
        for step in steps
        if "build_harness_artifact_index.py" in str(step.get("run", ""))
        and "-final" in str(step.get("run", ""))
    ]
    assert final_index_steps, "workflow 缺少最终 artifact index 步骤"
    final_index = final_index_steps[0]
    assert steps.index(final_index) > steps.index(summary_steps[-1]), (
        "最终 artifact index 必须晚于汇总步骤，覆盖 ci-summary 文件"
    )
    assert final_index.get("continue-on-error") is not True, (
        "最终 artifact index 失败必须使 job 失败"
    )
    assert final_index.get("if") == "always()"
