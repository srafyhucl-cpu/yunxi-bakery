"""Harness P1 运行观测合同测试。"""

from __future__ import annotations

from pathlib import Path

from scripts import harness_run_manifest, observe_harness_runs


def _manifest(run_id: str, parent_run_id: str | None = None) -> dict[str, object]:
    return harness_run_manifest.build_manifest(
        task_id="T-HARNESS-EVAL-REGRESSION",
        trace_id="20260831-harness-observation-test",
        goal="验证运行观测指标",
        run_id=run_id,
        parent_run_id=parent_run_id,
        status="active",
        model_id="test-model",
        replayable=True,
        latency_ms=100,
        plan_summary="生成观测测试运行",
        recovery_point="继续观测测试",
        tool_call_count=2,
    )


def test_observation_reports_replay_and_recovery_coverage(tmp_path: Path) -> None:
    first = tmp_path / "first.run.json"
    second = tmp_path / "second.run.json"
    first.write_text(
        __import__("json").dumps(_manifest("run-observe-001")), encoding="utf-8"
    )
    second.write_text(
        __import__("json").dumps(_manifest("run-observe-002", "run-observe-001")),
        encoding="utf-8",
    )

    report = observe_harness_runs.build_report([first, second])

    assert report["status"] == "passed"
    assert report["metrics"]["total_runs"] == 2
    assert report["metrics"]["replayable_ratio"] == 1.0
    assert report["metrics"]["recovery_point_coverage"] == 1.0
    assert report["metrics"]["parent_link_coverage"] == 1.0


def test_observation_rejects_invalid_manifest(tmp_path: Path) -> None:
    path = tmp_path / "invalid.run.json"
    path.write_text("{}", encoding="utf-8")

    report = observe_harness_runs.build_report([path])

    assert report["status"] == "failed"
    assert report["issues"]
