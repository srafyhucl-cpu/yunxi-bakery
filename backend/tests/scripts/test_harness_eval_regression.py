"""Harness P1 自评回归脚本合同测试。"""

from __future__ import annotations

from pathlib import Path

from scripts import harness_eval_regression


def test_dataset_has_eight_registered_cases() -> None:
    dataset = harness_eval_regression.load_dataset()

    assert len(dataset["cases"]) == 8
    assert all(
        case["evaluator"] in harness_eval_regression.EVALUATORS
        for case in dataset["cases"]
    )


def test_regression_evaluation_passes() -> None:
    report = harness_eval_regression.evaluate_dataset(
        harness_eval_regression.load_dataset()
    )

    assert report["status"] == "passed", report["results"]
    assert report["summary"]["passed"] == 8
    assert report["summary"]["total"] == 8
    assert report["summary"]["ratio"] == 1.0
    assert report["summary"]["failure_classes"] == {"none": 8}


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
