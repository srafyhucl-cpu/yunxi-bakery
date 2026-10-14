"""客户长上下文摘要 smoke 脚本测试。"""

import json

import pytest

from scripts import check_customer_long_context_summary_smoke as smoke


@pytest.mark.asyncio
async def test_customer_long_context_summary_smoke_passes() -> None:
    checks = await smoke.run_smoke_checks()
    report = smoke.build_json_report(checks)

    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert {check.name for check in checks} >= {
        "summary.section_present",
        "history.recent_user_preserved",
        "budget.history_pressure_candidate",
        "tool_pressure.no_summary_candidate",
    }


def test_customer_long_context_summary_report_marks_failures() -> None:
    report = smoke.build_json_report(
        [
            smoke.SmokeCheck("ok", True),
            smoke.SmokeCheck("bad", False, "missing marker"),
        ]
    )

    assert report["status"] == "failed"
    assert report["failed"] == 1
    assert report["failed_names"] == ["bad"]


@pytest.mark.asyncio
async def test_customer_long_context_summary_main_outputs_json(capsys) -> None:
    exit_code = await smoke.main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["failed"] == 0
