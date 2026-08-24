"""知识库 audience 治理 smoke 脚本测试。"""

import json

import pytest

from scripts import check_knowledge_audience_governance_smoke as smoke


@pytest.mark.asyncio
async def test_knowledge_audience_governance_smoke_passes() -> None:
    checks = await smoke.run_smoke_checks()
    report = smoke.build_json_report(checks)

    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert {check.name for check in checks} >= {
        "audience.default_all_only",
        "audience.customer_all_plus_customer",
        "audience.employee_all_plus_employee",
        "governance.hidden_entries_excluded",
        "validity.window_entry_visible",
    }


def test_knowledge_audience_governance_report_marks_failures() -> None:
    report = smoke.build_json_report(
        [
            smoke.GovernanceSmokeCheck("ok", True),
            smoke.GovernanceSmokeCheck("bad", False, "leaked"),
        ]
    )

    assert report["status"] == "failed"
    assert report["failed"] == 1
    assert report["failed_names"] == ["bad"]


@pytest.mark.asyncio
async def test_knowledge_audience_governance_main_outputs_json(capsys) -> None:
    exit_code = await smoke.main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["failed"] == 0
