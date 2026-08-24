import json
from pathlib import Path

from scripts import check_preflight_business_contracts as contract_check


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_bom_report(path: Path, payload: dict[str, object]) -> None:
    path.write_bytes(
        b"\xef\xbb\xbf" + json.dumps(payload, ensure_ascii=False).encode("utf-8")
    )


def _valid_payload() -> dict[str, object]:
    return {
        "status": "failed",
        "checks": [
            {
                "key": "handoff_staff_userid_ready",
                "passed": False,
                "detail": "failed",
            },
            {
                "key": contract_check.BUSINESS_CONTRACT_CHECK_KEY,
                "passed": True,
                "detail": (
                    "total=7 failed=0 "
                    "checks=employee_agent_capability_contracts:passed, "
                    "customer_rag_golden_cases:passed, "
                    "knowledge_governance_plan:passed, "
                    "customer_memory_governance_plan:passed, "
                    "customer_observability_contract:passed, "
                    "miniapp_page_api_contract:passed, "
                    "github_reference_implementation_plan:passed"
                ),
            },
        ],
    }


def test_validate_preflight_report_accepts_business_contract_evidence() -> None:
    checks = contract_check.validate_preflight_report(_valid_payload())
    report = contract_check.build_json_report(checks, Path("preflight.json"))

    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert {check.name for check in checks} == {
        contract_check.BUSINESS_CONTRACT_CHECK_KEY,
        "contract.employee_agent_capability_contracts",
        "contract.customer_rag_golden_cases",
        "contract.knowledge_governance_plan",
        "contract.customer_memory_governance_plan",
        "contract.customer_observability_contract",
        "contract.miniapp_page_api_contract",
        "contract.github_reference_implementation_plan",
    }


def test_validate_preflight_report_rejects_missing_contract_check() -> None:
    checks = contract_check.validate_preflight_report({"checks": []})
    report = contract_check.build_json_report(checks, Path("preflight.json"))

    assert report["status"] == "failed"
    assert report["failed_names"] == [contract_check.BUSINESS_CONTRACT_CHECK_KEY]


def test_validate_preflight_report_rejects_missing_contract_label() -> None:
    payload = _valid_payload()
    payload["checks"][1]["detail"] = (
        "total=3 failed=0 checks=employee_agent_capability_contracts:passed"
    )

    checks = contract_check.validate_preflight_report(payload)
    report = contract_check.build_json_report(checks, Path("preflight.json"))

    assert report["status"] == "failed"
    assert "contract.customer_rag_golden_cases" in report["failed_names"]
    assert "contract.knowledge_governance_plan" in report["failed_names"]
    assert "contract.customer_memory_governance_plan" in report["failed_names"]
    assert "contract.customer_observability_contract" in report["failed_names"]
    assert "contract.miniapp_page_api_contract" in report["failed_names"]
    assert "contract.github_reference_implementation_plan" in report["failed_names"]


def test_validate_preflight_report_rejects_failed_contract_check() -> None:
    payload = _valid_payload()
    payload["checks"][1]["passed"] = False

    checks = contract_check.validate_preflight_report(payload)
    report = contract_check.build_json_report(checks, Path("preflight.json"))

    assert report["status"] == "failed"
    assert contract_check.BUSINESS_CONTRACT_CHECK_KEY in report["failed_names"]


def test_main_outputs_json_and_summary(tmp_path: Path, capsys) -> None:
    report_path = tmp_path / "preflight.json"
    _write_report(report_path, _valid_payload())

    json_exit_code = contract_check.main([str(report_path), "--json"])
    json_payload = json.loads(capsys.readouterr().out)
    summary_exit_code = contract_check.main([str(report_path), "--summary"])
    summary_output = capsys.readouterr().out

    assert json_exit_code == 0
    assert json_payload["status"] == "passed"
    assert summary_exit_code == 0
    assert "preflight_business_contracts status=passed" in summary_output
    assert "failed=0" in summary_output


def test_main_accepts_bom_preflight_report(tmp_path: Path, capsys) -> None:
    report_path = tmp_path / "preflight-bom.json"
    _write_bom_report(report_path, _valid_payload())

    exit_code = contract_check.main([str(report_path), "--summary"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "preflight_business_contracts status=passed" in output
    assert "failed=0" in output


def test_main_returns_two_for_unreadable_report(capsys) -> None:
    exit_code = contract_check.main(["missing-preflight.json", "--summary"])

    assert exit_code == 2
    assert "读取预检报告失败" in capsys.readouterr().err
