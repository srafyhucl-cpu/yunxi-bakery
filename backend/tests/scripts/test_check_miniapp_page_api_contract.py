import json

from scripts import check_miniapp_page_api_contract as contract_check


def test_miniapp_page_api_contract_passes_static_check() -> None:
    checks = contract_check.validate_contract(contract_check.load_contract())
    report = contract_check.build_json_report(checks)

    assert report["status"] == "passed"
    assert report["failed"] == 0


def test_miniapp_page_api_contract_detects_missing_page_and_api() -> None:
    checks = contract_check.validate_contract("pages/home/index")
    report = contract_check.build_json_report(checks)

    assert report["status"] == "failed"
    failed_names = set(report["failed_names"])
    assert "page.pages/profile/index" in failed_names
    assert "api./api/v1/miniapp/orders" in failed_names
    assert "pending_platform_api.GET /api/v1/miniapp/member/benefits" in failed_names


def test_miniapp_page_api_contract_detects_forbidden_directive() -> None:
    checks = contract_check.validate_contract("在 MiniApp 写业务规则")
    report = contract_check.build_json_report(checks)

    assert report["status"] == "failed"
    assert "forbidden.在 MiniApp 写业务规则" in report["failed_names"]


def test_miniapp_page_api_contract_main_outputs_json(capsys) -> None:
    exit_code = contract_check.main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["failed"] == 0


def test_miniapp_page_api_contract_main_outputs_summary(capsys) -> None:
    exit_code = contract_check.main(["--summary"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "miniapp_page_api_contract status=passed" in output
    assert "failed=0" in output
