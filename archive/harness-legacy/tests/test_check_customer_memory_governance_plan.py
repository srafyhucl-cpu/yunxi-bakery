import json

from scripts import check_customer_memory_governance_plan as plan_check


def test_customer_memory_governance_plan_passes_static_check() -> None:
    checks = plan_check.validate_plan(plan_check.load_plan())
    report = plan_check.build_json_report(checks)

    assert report["status"] == "passed"
    assert report["failed"] == 0


def test_customer_memory_governance_plan_detects_missing_terms() -> None:
    checks = plan_check.validate_plan("customer_profiles source_evidence_json")
    report = plan_check.build_json_report(checks)

    assert report["status"] == "failed"
    failed_names = set(report["failed_names"])
    assert "required.conversation_summaries" in failed_names
    assert "boundary.不能从会话摘要直接提升" in failed_names


def test_customer_memory_governance_plan_detects_forbidden_directive() -> None:
    checks = plan_check.validate_plan(
        plan_check.load_plan() + "\n把会话摘要直接写入 `customer_profiles`\n"
    )
    report = plan_check.build_json_report(checks)

    assert report["status"] == "failed"
    assert "forbidden.把会话摘要直接写入 `customer_profiles`" in report["failed_names"]


def test_customer_memory_governance_plan_main_outputs_json(capsys) -> None:
    exit_code = plan_check.main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["failed"] == 0


def test_customer_memory_governance_plan_main_outputs_summary(capsys) -> None:
    exit_code = plan_check.main(["--summary"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "customer_memory_governance_plan status=passed" in output
    assert "failed=0" in output
