"""生成真实客服会话 replay 接入操作包。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from app.service.agents.evaluation import write_json_report  # noqa: E402
from scripts.check_real_conversation_replay_coverage import (  # noqa: E402
    CUSTOMER_GOLDEN_FIXTURE_PATH,
    DEFAULT_MIN_PER_SCENARIO,
    load_required_sensitive_scenarios,
)
from scripts.check_real_conversation_replay_pool import (  # noqa: E402
    RAW_SOURCE_RETENTION_NOT_COMMITTED,
    REAL_SOURCE_TYPE,
)

DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-conversation-replay-intake-packet.json"
)
DEFAULT_DRAFT_FIXTURE_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-conversation-replay-draft.json"
)
DEFAULT_DRAFT_CHECK_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-conversation-replay-draft-check.json"
)
DEFAULT_REPLIES_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-conversation-replies-draft.json"
)
DEFAULT_COVERAGE_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-conversation-replay-coverage.json"
)
DEFAULT_CANDIDATE_AUDIT_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-replay-candidate-audit.json"
)
DEFAULT_ENTRY_DRAFT_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-replay-pool-entry-draft.json"
)
DEFAULT_POOL_MANIFEST_PATH = (
    ROOT_DIR / "tests" / "fixtures" / "customer_real_replay_pool_manifest_sample.json"
)
REQUIRED_SENSITIVE_SCENARIOS = load_required_sensitive_scenarios(
    CUSTOMER_GOLDEN_FIXTURE_PATH
)
DEFAULT_TARGET_COUNT = len(REQUIRED_SENSITIVE_SCENARIOS) * DEFAULT_MIN_PER_SCENARIO

REQUIRED_RAW_RECORD_FIELDS = (
    "golden_case_id",
    "user_message",
    "final_reply",
)
OPTIONAL_RAW_RECORD_FIELDS = (
    "case_id",
    "source",
    "group",
    "intent",
)
RAW_RECORD_FIELD_ALIASES = {
    "case_id": ("id", "conversation_id"),
    "golden_case_id": ("golden_id",),
    "user_message": ("query", "customer_message", "message", "user_text"),
    "final_reply": ("reply", "assistant_reply", "bot_reply", "answer"),
}
REDACTION_REQUIREMENTS = (
    "手机号、地址、open_id、union_id、客户姓名、完整订单号必须脱敏",
    "原始客服记录只允许保存在仓库外，不得提交到 git",
    "fixture metadata 必须声明 contains_sensitive_data=false",
    "fixture metadata 必须写明 source 和 redaction",
    "人工审核后才能生成 pool manifest 条目草稿",
)
INTAKE_RECORD_TEMPLATE = {
    "case_id": "<stable-real-redacted-case-id>",
    "golden_case_id": "<matching-customer-golden-case-id>",
    "source": "<real-redacted-customer-service-export>",
    "group": "<optional-business-group>",
    "intent": "<optional-intent>",
    "user_message": "<已脱敏用户问题，不含手机号、地址、open_id、客户姓名、完整订单号>",
    "final_reply": "<已脱敏客服回复或系统最终回复>",
}
INTAKE_HANDOFF_DECLARATION_TEMPLATE = {
    "source_type": REAL_SOURCE_TYPE,
    "contains_sensitive_data": False,
    "redaction_method": "<manual_redaction_v1|tool_redaction_plus_manual_review>",
    "redaction_reviewer": "<脱敏审核人>",
    "redaction_reviewed_at": "<YYYY-MM-DD>",
    "raw_source_retention": RAW_SOURCE_RETENTION_NOT_COMMITTED,
    "evidence_id": "<evidence-index-id>",
}
PRE_SUBMISSION_CHECKLIST = (
    {
        "id": "source_is_real_customer_conversation",
        "owner": "external_record_holder",
        "human_input_required": True,
        "description": "确认来源是真实客服会话导出，不是 tests/fixtures 合成样例",
    },
    {
        "id": "raw_source_kept_outside_repo",
        "owner": "external_record_holder",
        "human_input_required": True,
        "description": "确认原始客服记录只保存在仓库外，不提交到 git 或 reports",
    },
    {
        "id": "sensitive_fields_redacted",
        "owner": "redaction_reviewer",
        "human_input_required": True,
        "description": "确认手机号、地址、open_id、union_id、客户姓名和完整订单号已脱敏",
    },
    {
        "id": "coverage_target_reviewed",
        "owner": "redaction_reviewer",
        "human_input_required": True,
        "description": "确认六类事实敏感场景目标覆盖，每类至少 5 条",
    },
    {
        "id": "evidence_id_registered",
        "owner": "repo_maintainer",
        "human_input_required": False,
        "description": "确认 evidence ID 将登记到 harness evidence-index",
    },
)


def build_real_replay_intake_packet(
    *,
    source_description: str = "external_redacted_customer_service_export",
    operator: str = "manual_reviewer",
    evidence_id: str = "E-P17B-REAL-REPLAY-INTAKE",
    target_count: int = DEFAULT_TARGET_COUNT,
    min_per_scenario: int = DEFAULT_MIN_PER_SCENARIO,
    draft_fixture_path: Path = DEFAULT_DRAFT_FIXTURE_PATH,
    pool_manifest_path: Path = DEFAULT_POOL_MANIFEST_PATH,
) -> dict[str, object]:
    assertions = build_packet_assertions(
        source_description=source_description,
        operator=operator,
        evidence_id=evidence_id,
        target_count=target_count,
        min_per_scenario=min_per_scenario,
    )
    failed = sum(1 for passed in assertions.values() if not passed)
    return {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "failed": failed,
        "operator": operator,
        "source_description": source_description,
        "evidence_id": evidence_id,
        "target_count": target_count,
        "min_per_scenario": min_per_scenario,
        "required_scenarios": list(REQUIRED_SENSITIVE_SCENARIOS),
        "raw_record_fields": list(
            REQUIRED_RAW_RECORD_FIELDS + OPTIONAL_RAW_RECORD_FIELDS
        ),
        "required_raw_record_fields": list(REQUIRED_RAW_RECORD_FIELDS),
        "optional_raw_record_fields": list(OPTIONAL_RAW_RECORD_FIELDS),
        "raw_record_field_aliases": {
            field: list(aliases) for field, aliases in RAW_RECORD_FIELD_ALIASES.items()
        },
        "redaction_requirements": list(REDACTION_REQUIREMENTS),
        "pre_submission_checklist": build_pre_submission_checklist(),
        "handoff_template": build_handoff_template(),
        "commands": build_command_plan(
            draft_fixture_path=draft_fixture_path,
            pool_manifest_path=pool_manifest_path,
            evidence_id=evidence_id,
            min_per_scenario=min_per_scenario,
        ),
        "assertions": assertions,
        "boundaries": {
            "raw_customer_conversation_read": False,
            "real_customer_data_committed": False,
            "business_database_read": False,
            "external_llm_called": False,
            "synthetic_samples_count_as_real": False,
            "readiness_changed": False,
        },
        "next_gate": (
            "python scripts\\check_real_conversation_replay_intake_readiness.py "
            "--require-real --summary"
        ),
    }


def build_pre_submission_checklist() -> list[dict[str, object]]:
    return [dict(item) for item in PRE_SUBMISSION_CHECKLIST]


def build_packet_assertions(
    *,
    source_description: str,
    operator: str,
    evidence_id: str,
    target_count: int,
    min_per_scenario: int,
) -> dict[str, bool]:
    return {
        "source_description.present": bool(source_description.strip()),
        "operator.present": bool(operator.strip()),
        "evidence_id.present": bool(evidence_id.strip()),
        "target_count.covers_required_scenarios": target_count
        >= len(REQUIRED_SENSITIVE_SCENARIOS) * min_per_scenario,
        "min_per_scenario.positive": min_per_scenario > 0,
    }


def build_command_plan(
    *,
    draft_fixture_path: Path,
    pool_manifest_path: Path,
    evidence_id: str,
    min_per_scenario: int,
) -> list[dict[str, object]]:
    return [
        *build_fixture_preparation_commands(
            draft_fixture_path=draft_fixture_path,
            evidence_id=evidence_id,
            min_per_scenario=min_per_scenario,
        ),
        *build_pool_admission_commands(
            draft_fixture_path=draft_fixture_path,
            pool_manifest_path=pool_manifest_path,
            evidence_id=evidence_id,
        ),
    ]


def build_handoff_template() -> dict[str, object]:
    return {
        "handoff_declaration": dict(INTAKE_HANDOFF_DECLARATION_TEMPLATE),
        "records": [dict(INTAKE_RECORD_TEMPLATE)],
    }


def build_fixture_preparation_commands(
    *,
    draft_fixture_path: Path,
    evidence_id: str,
    min_per_scenario: int,
) -> list[dict[str, object]]:
    return [
        build_command_step(
            "export_redacted_fixture",
            (
                "python scripts\\export_real_conversation_replay_fixture.py "
                "--input <仓库外已脱敏客服记录.jsonl> "
                "--source <真实脱敏来源标识> "
                f"--output {draft_fixture_path} --summary"
            ),
            human_input_required=True,
        ),
        build_command_step(
            "check_replay_contract",
            (
                "python scripts\\check_real_conversation_replay.py "
                f"--fixture {draft_fixture_path} "
                f"--json-out {DEFAULT_DRAFT_CHECK_PATH} "
                f"--replies-json-out {DEFAULT_REPLIES_PATH} --summary"
            ),
            human_input_required=False,
        ),
        build_command_step(
            "check_sensitive_scenario_coverage",
            (
                "python scripts\\check_real_conversation_replay_coverage.py "
                f"--fixture {draft_fixture_path} "
                f"--min-per-scenario {min_per_scenario} "
                f"--json-out {DEFAULT_COVERAGE_PATH} --summary"
            ),
            human_input_required=False,
        ),
        build_command_step(
            "audit_candidate_fixture",
            (
                "python scripts\\audit_real_conversation_replay_candidate.py "
                f"--fixture {draft_fixture_path} "
                "--require-fixture "
                f"--source-type {REAL_SOURCE_TYPE} "
                "--redaction-method <脱敏方法> "
                "--redaction-reviewer <审核人> "
                "--redaction-reviewed-at <YYYY-MM-DD> "
                f"--raw-source-retention {RAW_SOURCE_RETENTION_NOT_COMMITTED} "
                f"--evidence-id {evidence_id} "
                f"--json-out {DEFAULT_CANDIDATE_AUDIT_PATH} --summary"
            ),
            human_input_required=True,
        ),
    ]


def build_pool_admission_commands(
    *,
    draft_fixture_path: Path,
    pool_manifest_path: Path,
    evidence_id: str,
) -> list[dict[str, object]]:
    return [
        build_command_step(
            "prepare_pool_entry_draft",
            (
                "python scripts\\prepare_real_conversation_replay_pool_entry.py "
                f"--fixture {draft_fixture_path} "
                "--name <真实脱敏样本池名称> "
                f"--evidence-id {evidence_id} "
                "--redaction-method <脱敏方法> "
                "--redaction-reviewer <审核人> "
                "--redaction-reviewed-at <YYYY-MM-DD> "
                f"--source-type {REAL_SOURCE_TYPE} "
                f"--raw-source-retention {RAW_SOURCE_RETENTION_NOT_COMMITTED} "
                f"--json-out {DEFAULT_ENTRY_DRAFT_PATH} --summary"
            ),
            human_input_required=True,
        ),
        build_command_step(
            "verify_pool_strict_gate",
            (
                "python scripts\\check_real_conversation_replay_pool.py "
                f"--manifest {pool_manifest_path} --require-real --summary"
            ),
            human_input_required=True,
        ),
        build_command_step(
            "verify_intake_strict_gate",
            (
                "python scripts\\check_real_conversation_replay_intake_readiness.py "
                f"--manifest {pool_manifest_path} --require-real --summary"
            ),
            human_input_required=False,
        ),
    ]


def build_command_step(
    step: str,
    command: str,
    *,
    human_input_required: bool,
) -> dict[str, object]:
    return {
        "step": step,
        "command": command,
        "writes_sensitive_data": False,
        "human_input_required": human_input_required,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build real conversation replay intake packet"
    )
    parser.add_argument(
        "--source-description",
        default="external_redacted_customer_service_export",
        help="真实客服记录来源说明，不写入原始内容",
    )
    parser.add_argument("--operator", default="manual_reviewer", help="执行或审核人")
    parser.add_argument(
        "--evidence-id",
        default="E-P17B-REAL-REPLAY-INTAKE",
        help="证据索引 ID",
    )
    parser.add_argument(
        "--target-count",
        type=int,
        default=DEFAULT_TARGET_COUNT,
        help="计划接入的真实脱敏会话数量",
    )
    parser.add_argument(
        "--min-per-scenario",
        type=int,
        default=DEFAULT_MIN_PER_SCENARIO,
        help="每个事实敏感场景最少样本数",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="写入接入操作包 JSON 路径",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_real_replay_intake_packet(
        source_description=args.source_description,
        operator=args.operator,
        evidence_id=args.evidence_id,
        target_count=args.target_count,
        min_per_scenario=args.min_per_scenario,
    )
    if args.json_out is not None:
        write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "real_conversation_replay_intake_packet "
            f"status={report['status']} failed={report['failed']} "
            f"target_count={report['target_count']}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_text_report(report: dict[str, object]) -> None:
    print("real_conversation_replay_intake_packet")
    print(
        f"status={report['status']} failed={report['failed']} "
        f"target_count={report['target_count']}"
    )
    for command in report["commands"]:
        print(f"STEP {command['step']}: {command['command']}")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
