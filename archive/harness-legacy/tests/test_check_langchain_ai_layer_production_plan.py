"""LangChain AI 应用层生产增强计划静态验收测试。"""

from __future__ import annotations

import json

from scripts import check_langchain_ai_layer_production_plan as plan_check


def test_langchain_ai_layer_production_plan_passes_static_check() -> None:
    checks = plan_check.validate_plan(plan_check.load_plan())
    report = plan_check.build_json_report(checks)

    assert report["status"] == "passed"
    assert report["failed"] == 0


def test_langchain_ai_layer_production_plan_detects_stale_status() -> None:
    checks = plan_check.validate_plan("状态：计划冻结，待执行")
    report = plan_check.build_json_report(checks)

    assert report["status"] == "failed"
    assert "stale.状态：计划冻结，待执行" in report["failed_names"]
    assert "status.状态：持续执行中" in report["failed_names"]
    assert "status.P0-P14c 已完成" in report["failed_names"]


def test_langchain_ai_layer_production_plan_detects_missing_boundary() -> None:
    checks = plan_check.validate_plan("状态：持续执行中")
    report = plan_check.build_json_report(checks)

    assert report["status"] == "failed"
    assert "boundary.合成覆盖样例不等同真实客服样本池" in report["failed_names"]
    assert (
        "artifact.scripts/check_real_conversation_replay_coverage.py"
        in report["failed_names"]
    )
    assert (
        "artifact.scripts/build_real_conversation_replay_intake_packet.py"
        in report["failed_names"]
    )
    assert (
        "artifact.scripts/audit_real_conversation_replay_candidate.py"
        in report["failed_names"]
    )
    assert (
        "artifact.scripts/check_langsmith_production_rollout.py"
        in report["failed_names"]
    )
    assert (
        "artifact.scripts/build_langsmith_production_enablement_packet.py"
        in report["failed_names"]
    )
    assert (
        "artifact.scripts/check_langchain_ai_layer_capacity.py"
        in report["failed_names"]
    )
    assert (
        "artifact.scripts/report_rag_shadow_observability.py" in report["failed_names"]
    )
    assert (
        "artifact.scripts/report_rag_shadow_log_observability.py"
        in report["failed_names"]
    )
    assert (
        "artifact.scripts/build_rag_shadow_log_intake_packet.py"
        in report["failed_names"]
    )
    assert (
        "artifact.scripts/build_langchain_release_evidence_packet.py"
        in report["failed_names"]
    )
    assert (
        "artifact.scripts/build_langchain_portfolio_evidence_packet.py"
        in report["failed_names"]
    )
    assert (
        "artifact.scripts/build_langchain_external_evidence_handoff_packet.py"
        in report["failed_names"]
    )
    assert "external_handoff_contract.action_groups" in report["failed_names"]
    assert "external_handoff_contract.action_group_details" in report["failed_names"]
    assert (
        "external_handoff_contract.pre_submission_checklist_summary"
        in report["failed_names"]
    )
    assert "external_handoff_contract.precheck_items=10" in report["failed_names"]
    assert "external_handoff_contract.--markdown-out" in report["failed_names"]
    assert (
        "external_handoff_contract.LangChain 外部证据交接包" in report["failed_names"]
    )


def test_langchain_ai_layer_production_plan_main_outputs_json(capsys) -> None:
    exit_code = plan_check.main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["failed"] == 0


def test_langchain_ai_layer_production_plan_main_outputs_summary(capsys) -> None:
    exit_code = plan_check.main(["--summary"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "langchain_ai_layer_production_plan status=passed" in output
    assert "failed=0" in output
