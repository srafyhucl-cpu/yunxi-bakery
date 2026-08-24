from __future__ import annotations

import json
from pathlib import Path

from scripts import build_langchain_external_evidence_handoff_packet as handoff


def build_portfolio_stub() -> dict[str, object]:
    return {
        "verified_evidence_ready": True,
        "external_evidence_complete": False,
        "portfolio_complete": False,
        "missing_actions": [
            "refresh_current_version_agent_eval",
            "refresh_strict_production_release_evidence",
            "provide_and_approve_redacted_real_replay_samples",
            "provide_redacted_rag_shadow_log_input",
            "complete_controlled_planned_hybrid_gray_release",
            "obtain_export_approval_and_enable_langsmith_sampling",
            "cover_each_fact_sensitive_scenario_with_real_replays",
        ],
        "stage_readiness": {
            "E1_real_replay": {
                "ready": False,
                "action": "provide_and_approve_redacted_real_replay_samples",
            },
            "E2_real_rag_shadow_log": {
                "ready": False,
                "action": "provide_redacted_rag_shadow_log_input",
            },
            "E3_planned_hybrid_gray_release": {
                "ready": False,
                "action": "complete_controlled_planned_hybrid_gray_release",
            },
            "E4_langsmith_production_export": {
                "ready": False,
                "action": "obtain_export_approval_and_enable_langsmith_sampling",
            },
            "E5_real_fact_sensitive_coverage": {
                "ready": False,
                "action": "cover_each_fact_sensitive_scenario_with_real_replays",
            },
        },
    }


def test_external_evidence_handoff_collects_replay_and_rag_packets() -> None:
    report = handoff.build_external_evidence_handoff_packet(
        operator="reviewer_a",
        handoff_evidence_id="E-HANDOFF-001",
        real_replay_evidence_id="E-REAL-001",
        rag_shadow_log_evidence_id="E-RAG-001",
        portfolio=build_portfolio_stub(),
    )

    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert report["external_evidence_complete"] is False
    assert report["portfolio_complete"] is False
    readiness_truth = report["readiness_truth"]
    assert readiness_truth["candidate_ready"] is False
    assert readiness_truth["real_sample_ready"] is False
    assert readiness_truth["shadow_log_ready"] is False
    assert readiness_truth["external_evidence_complete"] is False
    assert readiness_truth["portfolio_complete"] is False
    assert readiness_truth["readiness_changed"] is False
    assert (
        readiness_truth["stage_readiness"]["E1_real_replay"]["action"]
        == "provide_and_approve_redacted_real_replay_samples"
    )
    false_reason_names = {
        item["name"] for item in readiness_truth["false_readiness_reasons"]
    }
    assert "candidate_ready" in false_reason_names
    assert "E2_real_rag_shadow_log" in false_reason_names
    assert report["boundaries"]["readiness_changed"] is False
    assert (
        report["boundaries"]["missing_external_evidence_treated_as_complete"] is False
    )

    real_replay = report["handoff_packets"]["real_replay"]
    assert real_replay["readiness"]["candidate_ready"] is False
    assert real_replay["readiness"]["real_sample_ready"] is False
    assert (
        real_replay["handoff_template"]["handoff_declaration"]["evidence_id"]
        == "<evidence-index-id>"
    )
    checklist_ids = {item["id"] for item in real_replay["pre_submission_checklist"]}
    assert "source_is_real_customer_conversation" in checklist_ids
    assert "sensitive_fields_redacted" in checklist_ids
    assert any(
        "--evidence-id E-REAL-001" in command["command"]
        for command in real_replay["commands"]
    )

    rag_shadow_log = report["handoff_packets"]["rag_shadow_log"]
    assert rag_shadow_log["readiness"]["shadow_log_ready"] is False
    assert rag_shadow_log["handoff_template"]["metadata"]["evidence_id"] == "E-RAG-001"
    rag_checklist_ids = {
        item["id"] for item in rag_shadow_log["pre_submission_checklist"]
    }
    assert "source_is_real_rag_shadow_log" in rag_checklist_ids
    assert "query_text_redacted" in rag_checklist_ids
    assert "--require-input" in rag_shadow_log["commands"][0]["command"]

    checklist_summary = report["pre_submission_checklist_summary"]
    assert checklist_summary["total_items"] == 10
    assert checklist_summary["human_input_required_items"] == 9
    assert checklist_summary["automation_safe_items"] == 1
    assert checklist_summary["owners"] == [
        "external_record_holder",
        "redaction_reviewer",
        "repo_maintainer",
        "external_log_holder",
    ]
    source_counts = {
        source["source"]: source["item_count"]
        for source in checklist_summary["sources"]
    }
    assert source_counts == {"real_replay": 5, "rag_shadow_log": 5}


def test_external_evidence_handoff_exposes_all_missing_external_inputs() -> None:
    report = handoff.build_external_evidence_handoff_packet(
        portfolio=build_portfolio_stub()
    )

    stages = {item["stage"] for item in report["required_external_inputs"]}
    assert stages == {
        "E1_real_replay",
        "E2_real_rag_shadow_log",
        "E3_planned_hybrid_gray_release",
        "E4_langsmith_production_export",
        "E5_real_fact_sensitive_coverage",
    }
    assert report["missing_actions"] == build_portfolio_stub()["missing_actions"]
    assert report["action_groups"] == {
        "local_evidence_refresh_actions": [
            "refresh_current_version_agent_eval",
            "refresh_strict_production_release_evidence",
        ],
        "external_handoff_actions": [
            "provide_and_approve_redacted_real_replay_samples",
            "provide_redacted_rag_shadow_log_input",
            "complete_controlled_planned_hybrid_gray_release",
            "obtain_export_approval_and_enable_langsmith_sampling",
            "cover_each_fact_sensitive_scenario_with_real_replays",
        ],
    }
    assert report["action_group_details"]["local_evidence_refresh"] == {
        "owner": "repo_maintainer",
        "human_input_required": False,
        "actions": [
            "refresh_current_version_agent_eval",
            "refresh_strict_production_release_evidence",
        ],
    }
    assert report["action_group_details"]["external_handoff"] == {
        "owner": "external_record_holder_or_compliance_reviewer",
        "human_input_required": True,
        "actions": [
            "provide_and_approve_redacted_real_replay_samples",
            "provide_redacted_rag_shadow_log_input",
            "complete_controlled_planned_hybrid_gray_release",
            "obtain_export_approval_and_enable_langsmith_sampling",
            "cover_each_fact_sensitive_scenario_with_real_replays",
        ],
    }
    assert [step["step"] for step in report["handoff_sequence"]] == [
        "collect_real_replay_input_outside_repo",
        "collect_rag_shadow_log_input_outside_repo",
        "refresh_portfolio_completion_gate",
    ]


def test_external_evidence_handoff_rejects_missing_handoff_id() -> None:
    report = handoff.build_external_evidence_handoff_packet(
        handoff_evidence_id=" ",
        portfolio=build_portfolio_stub(),
    )

    assert report["status"] == "failed"
    assert report["assertions"]["handoff_evidence_id.present"] is False


def test_external_evidence_handoff_cli_writes_json(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "external-handoff.json"

    exit_code = handoff.main(
        [
            "--operator",
            "reviewer_b",
            "--handoff-evidence-id",
            "E-HANDOFF-002",
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "local_refresh_actions=" in captured
    assert "external_handoff_actions=5" in captured
    assert "precheck_items=10" in captured
    assert payload["operator"] == "reviewer_b"
    assert payload["handoff_evidence_id"] == "E-HANDOFF-002"
    assert payload["external_evidence_complete"] is False


def test_external_evidence_handoff_cli_writes_markdown(tmp_path: Path) -> None:
    json_output_path = tmp_path / "external-handoff.json"
    markdown_output_path = tmp_path / "external-handoff.md"

    exit_code = handoff.main(
        [
            "--operator",
            "reviewer_c",
            "--handoff-evidence-id",
            "E-HANDOFF-003",
            "--json-out",
            str(json_output_path),
            "--markdown-out",
            str(markdown_output_path),
            "--summary",
        ]
    )

    markdown = markdown_output_path.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "# LangChain 外部证据交接包" in markdown
    assert "- candidate_ready: `false`" in markdown
    assert "- portfolio_complete: `false`" in markdown
    assert "## 提交前自检摘要" in markdown
    assert "- total_items: `10`" in markdown
    assert "`source_is_real_customer_conversation`" in markdown
    assert "`source_is_real_rag_shadow_log`" in markdown
    assert "## 真实 replay 交接命令" in markdown
    assert "## RAG shadow log 交接命令" in markdown
    assert "- readiness_changed: `false`" in markdown
