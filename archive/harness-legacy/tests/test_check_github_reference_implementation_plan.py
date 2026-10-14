import json

from scripts import check_github_reference_implementation_plan as plan_check


def test_github_reference_implementation_plan_passes_static_check() -> None:
    checks = plan_check.validate_plan(plan_check.load_plan())
    report = plan_check.build_json_report(checks)

    assert report["status"] == "passed"
    assert report["failed"] == 0


def test_github_reference_implementation_plan_detects_missing_boundary() -> None:
    checks = plan_check.validate_plan("阶段 0 已冻结")
    report = plan_check.build_json_report(checks)

    assert report["status"] == "failed"
    failed_names = set(report["failed_names"])
    assert "boundary.员工助手不能 Agent 化成自由推理" in failed_names
    assert "artifact.bot-capability-matrix.md" in failed_names
    assert "langgraph_limit.不进入客户实时回复" in failed_names


def test_github_reference_implementation_plan_detects_forbidden_directive() -> None:
    checks = plan_check.validate_plan("迁移客户机器人热路径到 LangChain")
    report = plan_check.build_json_report(checks)

    assert report["status"] == "failed"
    assert "forbidden.迁移客户机器人热路径到 LangChain" in report["failed_names"]


def test_github_reference_implementation_plan_main_outputs_json(capsys) -> None:
    exit_code = plan_check.main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["failed"] == 0


def test_github_reference_implementation_plan_main_outputs_summary(capsys) -> None:
    exit_code = plan_check.main(["--summary"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "github_reference_implementation_plan status=passed" in output
    assert "failed=0" in output
