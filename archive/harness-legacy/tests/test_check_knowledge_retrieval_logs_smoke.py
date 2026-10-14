"""知识库检索命中日志 smoke 脚本测试。"""

import json

import pytest

from scripts import check_knowledge_retrieval_logs_smoke as smoke


@pytest.mark.asyncio
async def test_knowledge_retrieval_logs_smoke_passes() -> None:
    checks = await smoke.run_smoke_checks()
    report = smoke.build_json_report(checks)

    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert {check.name for check in checks} >= {
        "customer.hit_log_written",
        "employee.hit_log_written",
        "fallback.no_match_logged",
        "log.count",
    }


def test_knowledge_retrieval_logs_report_marks_failures() -> None:
    report = smoke.build_json_report(
        [
            smoke.RetrievalLogSmokeCheck("ok", True),
            smoke.RetrievalLogSmokeCheck("bad", False, "missing"),
        ]
    )

    assert report["status"] == "failed"
    assert report["failed"] == 1
    assert report["failed_names"] == ["bad"]


@pytest.mark.asyncio
async def test_knowledge_retrieval_logs_main_outputs_json(capsys) -> None:
    exit_code = await smoke.main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["failed"] == 0
