import json

from scripts import check_knowledge_governance_plan as plan_check


def test_knowledge_governance_plan_passes_static_check() -> None:
    checks = plan_check.validate_plan(plan_check.load_plan())
    report = plan_check.build_json_report(checks)

    assert report["status"] == "passed"
    assert report["failed"] == 0


def test_knowledge_governance_plan_detects_missing_terms() -> None:
    checks = plan_check.validate_plan("knowledge_base audience")
    report = plan_check.build_json_report(checks)

    assert report["status"] == "failed"
    failed_names = set(report["failed_names"])
    assert "required.review_status" in failed_names
    assert "boundary.拆分 `knowledge_base` 为多张主表" in failed_names


def test_knowledge_governance_plan_main_outputs_json(capsys) -> None:
    exit_code = plan_check.main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["failed"] == 0


def test_knowledge_governance_plan_main_outputs_summary(capsys) -> None:
    exit_code = plan_check.main(["--summary"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "knowledge_governance_plan status=passed" in output
    assert "failed=0" in output
