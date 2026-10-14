"""Harness P1 自评回归脚本合同测试。"""

from __future__ import annotations

from pathlib import Path

from scripts import harness_eval_regression


def test_dataset_version_and_registered_cases() -> None:
    dataset = harness_eval_regression.load_dataset()

    assert dataset["dataset_version"] == "1.2.0"
    assert len(dataset["cases"]) == 18
    assert all(
        case["evaluator"] in harness_eval_regression.EVALUATORS
        for case in dataset["cases"]
    )


def test_regression_evaluation_passes() -> None:
    report = harness_eval_regression.evaluate_dataset(
        harness_eval_regression.load_dataset()
    )

    assert report["status"] == "passed", report["results"]
    assert report["summary"]["passed"] == 18
    assert report["summary"]["total"] == 18
    assert report["summary"]["ratio"] == 1.0
    assert report["summary"]["failure_classes"] == {"none": 18}


def test_real_incident_contracts_pass() -> None:
    root = Path(__file__).resolve().parents[2]
    for evaluator_name in (
        "shallow_clone_history_contract",
        "ci_corpus_contract",
        "state_snapshot_parent_contract",
        "artifact_failure_visibility_contract",
    ):
        assert (
            harness_eval_regression.EVALUATORS[evaluator_name](root)["passed"] is True
        )


def test_p0_gate_evaluator_matches_nine_required_checks() -> None:
    result = harness_eval_regression.evaluate_p0_gate_contract(Path("."))

    assert result["passed"] is True
    assert result["details"] == "checks=9"


def test_report_does_not_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "eval.json"
    path.write_text("existing", encoding="utf-8")

    try:
        harness_eval_regression.write_report(path, {"status": "passed"})
    except FileExistsError:
        pass
    else:
        raise AssertionError("自评报告不应覆盖既有文件")

    assert path.read_text(encoding="utf-8") == "existing"
