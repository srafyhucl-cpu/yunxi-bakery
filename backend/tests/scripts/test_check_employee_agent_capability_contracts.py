import json

from scripts import check_employee_agent_capability_contracts as contract_check


def test_employee_agent_capability_contracts_pass() -> None:
    checks = contract_check.run_checks()
    report = contract_check.build_json_report(checks)

    assert report["status"] == "passed"
    assert report["failed"] == 0


def test_employee_agent_capability_contracts_detect_missing_contract() -> None:
    check = contract_check._set_check("sample", {"a", "b"}, {"a"})

    assert not check.passed
    assert "b" in check.detail


def test_employee_agent_capability_contracts_main_outputs_json(capsys) -> None:
    exit_code = contract_check.main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["failed"] == 0


def test_employee_agent_capability_contracts_main_outputs_summary(capsys) -> None:
    exit_code = contract_check.main(["--summary"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "total=66 failed=0" in output
