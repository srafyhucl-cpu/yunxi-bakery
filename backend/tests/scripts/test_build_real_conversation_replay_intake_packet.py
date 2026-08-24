from __future__ import annotations

import json
from pathlib import Path

from scripts import export_real_conversation_replay_fixture
from scripts import build_real_conversation_replay_intake_packet as intake_packet


def test_intake_packet_contains_external_operator_command_chain() -> None:
    report = intake_packet.build_real_replay_intake_packet(
        source_description="external_helpdesk_export_2026_07",
        operator="reviewer_a",
        evidence_id="E-REAL-001",
    )

    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert report["boundaries"]["raw_customer_conversation_read"] is False
    assert report["boundaries"]["real_customer_data_committed"] is False
    assert "order" in report["required_scenarios"]
    assert "refund" in report["required_scenarios"]
    assert (
        report["handoff_template"]["handoff_declaration"]["source_type"]
        == "real_customer_conversation"
    )
    assert (
        report["handoff_template"]["handoff_declaration"]["contains_sensitive_data"]
        is False
    )
    assert (
        report["handoff_template"]["handoff_declaration"]["raw_source_retention"]
        == "not_committed"
    )
    handoff_record = report["handoff_template"]["records"][0]
    assert "user_message" in handoff_record
    assert "final_reply" in handoff_record
    assert "messages" not in handoff_record

    command_steps = [item["step"] for item in report["commands"]]
    assert command_steps == [
        "export_redacted_fixture",
        "check_replay_contract",
        "check_sensitive_scenario_coverage",
        "audit_candidate_fixture",
        "prepare_pool_entry_draft",
        "verify_pool_strict_gate",
        "verify_intake_strict_gate",
    ]
    assert any("--require-real" in item["command"] for item in report["commands"])
    assert any(
        "--source-type real_customer_conversation" in item["command"]
        for item in report["commands"]
    )
    assert any(
        "--raw-source-retention not_committed" in item["command"]
        for item in report["commands"]
    )
    audit_command = next(
        item["command"]
        for item in report["commands"]
        if item["step"] == "audit_candidate_fixture"
    )
    assert "--json-out" in audit_command

    checklist = report["pre_submission_checklist"]
    checklist_ids = {item["id"] for item in checklist}
    assert checklist_ids == {
        "source_is_real_customer_conversation",
        "raw_source_kept_outside_repo",
        "sensitive_fields_redacted",
        "coverage_target_reviewed",
        "evidence_id_registered",
    }
    assert all("owner" in item for item in checklist)
    assert all("human_input_required" in item for item in checklist)
    assert report["boundaries"]["readiness_changed"] is False


def test_handoff_template_matches_exporter_input_contract(tmp_path: Path) -> None:
    report = intake_packet.build_real_replay_intake_packet()
    handoff_template = report["handoff_template"]
    handoff_record = handoff_template["records"][0]
    handoff_record.update(
        {
            "case_id": "real-redacted-refund-001",
            "golden_case_id": "customer-refund-sensitive-001",
            "source": "real_redacted_customer_service_export",
            "group": "refund_after_sales",
            "intent": "faq_after_sales",
            "user_message": "用户询问退款进度，联系方式和订单标识均已脱敏。",
            "final_reply": "退款需要按订单状态和制作进度确认，我会协助转人工核对。",
        }
    )
    input_path = tmp_path / "handoff-input.json"
    output_path = tmp_path / "replay-fixture.json"
    input_path.write_text(
        json.dumps(handoff_template, ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = export_real_conversation_replay_fixture.main(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--source",
            "real_redacted_customer_service_export",
            "--summary",
        ]
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["cases"][0]["user_message"] == handoff_record["user_message"]
    assert payload["cases"][0]["final_reply"] == handoff_record["final_reply"]


def test_intake_packet_rejects_insufficient_target_count() -> None:
    report = intake_packet.build_real_replay_intake_packet(target_count=1)

    assert report["status"] == "failed"
    assert report["assertions"]["target_count.covers_required_scenarios"] is False


def test_intake_packet_cli_writes_json(tmp_path: Path) -> None:
    output_path = tmp_path / "packet.json"

    exit_code = intake_packet.main(
        [
            "--operator",
            "reviewer_b",
            "--evidence-id",
            "E-REAL-002",
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["operator"] == "reviewer_b"
    assert payload["evidence_id"] == "E-REAL-002"
