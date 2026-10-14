import json

from scripts import check_customer_observability_contract as contract_check


def test_customer_observability_contract_passes_static_check() -> None:
    checks = contract_check.validate_contract(contract_check.load_contract())
    report = contract_check.build_json_report(checks)

    assert report["status"] == "passed"
    assert report["failed"] == 0


def test_customer_observability_contract_detects_missing_metrics() -> None:
    checks = contract_check.validate_contract("trace_id session_id")
    report = contract_check.build_json_report(checks)

    assert report["status"] == "failed"
    failed_names = set(report["failed_names"])
    assert "metric.knowledge_hit_rate" in failed_names
    assert "field.channel_type" in failed_names
    assert "boundary.不改客户机器人热路径" in failed_names


def test_customer_observability_contract_detects_forbidden_directive() -> None:
    checks = contract_check.validate_contract("用指标结果自动改写回复")
    report = contract_check.build_json_report(checks)

    assert report["status"] == "failed"
    assert "forbidden.用指标结果自动改写回复" in report["failed_names"]


def test_customer_observability_contract_main_outputs_json(capsys) -> None:
    exit_code = contract_check.main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["failed"] == 0


def test_customer_observability_contract_main_outputs_summary(capsys) -> None:
    exit_code = contract_check.main(["--summary"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "customer_observability_contract status=passed" in output
    assert "failed=0" in output
