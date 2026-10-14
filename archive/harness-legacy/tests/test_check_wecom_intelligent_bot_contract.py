import json

from scripts import check_wecom_intelligent_bot_contract as contract


def test_contract_checks_pass_for_current_router_and_document() -> None:
    checks = contract.build_contract_checks()

    assert all(check.passed for check in checks)
    assert {check.key for check in checks} == {
        "document_exists",
        "documented_tool_names",
        "documented_tool_paths",
        "router_paths",
    }


def test_json_report_includes_expected_tools() -> None:
    payload = contract.build_json_report([contract.ContractCheck("ok", True, "ready")])

    assert payload["status"] == "passed"
    assert payload["expected_tools"]["knowledge-answer"] == "/tools/knowledge-answer"
    assert "WECOM_BOT_PLUGIN_API_KEY" not in json.dumps(
        payload,
        ensure_ascii=False,
    )


def test_main_json_output_can_be_written_to_file(tmp_path) -> None:
    report_path = tmp_path / "reports" / "contract.json"

    exit_code = contract.main(["--json", "--output", str(report_path)])

    assert exit_code == 0
    assert report_path.read_bytes().startswith(contract.UTF8_BOM)
    payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    assert payload["status"] == "passed"


def test_main_refuses_to_overwrite_file(tmp_path, capsys) -> None:
    report_path = tmp_path / "contract.json"
    report_path.write_text("existing", encoding="utf-8")

    exit_code = contract.main(["--json", "--output", str(report_path)])

    assert exit_code == 2
    assert report_path.read_text(encoding="utf-8") == "existing"
    assert "拒绝覆盖" in capsys.readouterr().err
