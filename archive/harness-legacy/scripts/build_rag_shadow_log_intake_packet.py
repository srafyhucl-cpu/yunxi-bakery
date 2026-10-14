"""生成真实 RAG shadow log 仓库外交接操作包。"""

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
from scripts.report_rag_shadow_log_observability import (  # noqa: E402
    RAW_SOURCE_RETENTION_NOT_COMMITTED,
    REAL_SHADOW_LOG_SOURCE_TYPE,
    REDACTION_REQUIREMENTS,
    REQUIRED_METADATA_FIELDS,
    REQUIRED_RECORD_FIELDS,
)

DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "retrieval-shadow" / "rag-shadow-log-intake-packet.json"
)
DEFAULT_OBSERVABILITY_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "retrieval-shadow" / "rag-shadow-log-observability.json"
)
DEFAULT_RECOMMENDED_RECORD_COUNT = 30
OPTIONAL_RECORD_FIELDS = ("group",)
PRE_SUBMISSION_CHECKLIST = (
    {
        "id": "source_is_real_rag_shadow_log",
        "owner": "external_log_holder",
        "human_input_required": True,
        "check": (
            "确认输入来自真实用户 RAG 检索 shadow log，"
            "不是 golden case、合成样例或手写示例。"
        ),
    },
    {
        "id": "raw_shadow_log_kept_outside_repo",
        "owner": "external_log_holder",
        "human_input_required": True,
        "check": "确认原始生产检索日志只保存在仓库外，提交物仅包含已脱敏副本。",
    },
    {
        "id": "query_text_redacted",
        "owner": "redaction_reviewer",
        "human_input_required": True,
        "check": (
            "确认 records[].query 已移除手机号、地址、open_id、客户姓名、"
            "完整订单号和其他可识别个人或订单的信息。"
        ),
    },
    {
        "id": "metadata_proof_fields_present",
        "owner": "redaction_reviewer",
        "human_input_required": True,
        "check": (
            "确认 metadata.source_type、redaction_method、redaction_reviewer、"
            "redaction_reviewed_at、raw_source_retention 和 evidence_id 已填写。"
        ),
    },
    {
        "id": "evidence_id_registered",
        "owner": "repo_maintainer",
        "human_input_required": True,
        "check": "确认 evidence_id 已登记到 docs/harness-engineering/core/evidence-index.md。",
    },
)
HANDOFF_METADATA_TEMPLATE = {
    "source_type": REAL_SHADOW_LOG_SOURCE_TYPE,
    "contains_sensitive_data": False,
    "redaction_method": "<manual_redaction_v1|tool_redaction_plus_manual_review>",
    "redaction_reviewer": "<脱敏审核人>",
    "redaction_reviewed_at": "<YYYY-MM-DD>",
    "raw_source_retention": RAW_SOURCE_RETENTION_NOT_COMMITTED,
    "evidence_id": "<evidence-index-id>",
}
HANDOFF_RECORD_TEMPLATE = {
    "id": "<stable-redacted-shadow-log-id>",
    "group": "<optional-business-group>",
    "query": "<已脱敏检索问题，不含手机号、地址、open_id、客户姓名或完整订单号>",
    "baseline_top_keys": ["<hybrid-baseline-result-key>"],
}


def build_rag_shadow_log_intake_packet(
    *,
    source_description: str = "external_redacted_rag_shadow_log_export",
    operator: str = "manual_reviewer",
    evidence_id: str = "E-P19C-RAG-SHADOW-LOG-INTAKE",
    recommended_record_count: int = DEFAULT_RECOMMENDED_RECORD_COUNT,
    observability_output_path: Path = DEFAULT_OBSERVABILITY_OUTPUT_PATH,
) -> dict[str, object]:
    assertions = build_packet_assertions(
        source_description=source_description,
        operator=operator,
        evidence_id=evidence_id,
        recommended_record_count=recommended_record_count,
    )
    failed = sum(1 for passed in assertions.values() if not passed)
    return {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "failed": failed,
        "source_description": source_description,
        "operator": operator,
        "evidence_id": evidence_id,
        "recommended_record_count": recommended_record_count,
        "required_metadata_fields": list(REQUIRED_METADATA_FIELDS),
        "required_record_fields": list(REQUIRED_RECORD_FIELDS),
        "optional_record_fields": list(OPTIONAL_RECORD_FIELDS),
        "redaction_requirements": list(REDACTION_REQUIREMENTS),
        "handoff_template": build_handoff_template(
            operator=operator,
            evidence_id=evidence_id,
        ),
        "pre_submission_checklist": build_pre_submission_checklist(),
        "commands": build_command_plan(observability_output_path),
        "assertions": assertions,
        "boundaries": build_boundaries(),
        "readiness": {
            "shadow_log_ready": False,
            "reason": "external_redacted_input_not_provided_by_packet_builder",
        },
    }


def build_packet_assertions(
    *,
    source_description: str,
    operator: str,
    evidence_id: str,
    recommended_record_count: int,
) -> dict[str, bool]:
    return {
        "source_description.present": bool(source_description.strip()),
        "operator.present": bool(operator.strip()),
        "evidence_id.present": bool(evidence_id.strip()),
        "recommended_record_count.positive": recommended_record_count > 0,
        "observability_checker.present": (
            ROOT_DIR / "scripts" / "report_rag_shadow_log_observability.py"
        ).is_file(),
    }


def build_handoff_template(
    *,
    operator: str,
    evidence_id: str,
) -> dict[str, object]:
    metadata = dict(HANDOFF_METADATA_TEMPLATE)
    metadata["redaction_reviewer"] = operator
    metadata["evidence_id"] = evidence_id
    return {
        "metadata": metadata,
        "records": [dict(HANDOFF_RECORD_TEMPLATE)],
    }


def build_pre_submission_checklist() -> list[dict[str, object]]:
    return [dict(item) for item in PRE_SUBMISSION_CHECKLIST]


def build_command_plan(
    observability_output_path: Path,
) -> list[dict[str, object]]:
    return [
        build_command_step(
            "validate_redacted_shadow_log",
            (
                "python scripts\\report_rag_shadow_log_observability.py "
                "--input <仓库外已脱敏-rag-shadow-log.json> --require-input "
                f"--json-out {observability_output_path} --summary"
            ),
            human_input_required=True,
        ),
        build_command_step(
            "refresh_portfolio_evidence",
            (
                "python scripts\\build_langchain_portfolio_evidence_packet.py "
                "--require-verified-evidence --summary"
            ),
            human_input_required=False,
        ),
        build_command_step(
            "verify_production_plan",
            "python scripts\\check_langchain_ai_layer_production_plan.py --summary",
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
        "human_input_required": human_input_required,
    }


def build_boundaries() -> dict[str, bool]:
    return {
        "raw_production_log_read": False,
        "raw_production_log_committed": False,
        "business_database_read": False,
        "business_database_written": False,
        "external_llm_called": False,
        "production_hot_path_changed": False,
        "rag_retrieval_mode_changed": False,
        "readiness_changed": False,
        "missing_external_input_treated_as_ready": False,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build redacted RAG shadow log intake packet"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="写入 RAG shadow log 交接操作包",
    )
    parser.add_argument(
        "--source-description", default="external_redacted_rag_shadow_log_export"
    )
    parser.add_argument("--operator", default="manual_reviewer")
    parser.add_argument("--evidence-id", default="E-P19C-RAG-SHADOW-LOG-INTAKE")
    parser.add_argument(
        "--recommended-record-count",
        type=int,
        default=DEFAULT_RECOMMENDED_RECORD_COUNT,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_rag_shadow_log_intake_packet(
        source_description=args.source_description,
        operator=args.operator,
        evidence_id=args.evidence_id,
        recommended_record_count=args.recommended_record_count,
    )
    if args.json_out is not None:
        write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print_summary(report)
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_summary(report: dict[str, object]) -> None:
    readiness = report["readiness"]
    print(
        "rag_shadow_log_intake_packet "
        f"status={report['status']} failed={report['failed']} "
        f"shadow_log_ready={str(readiness['shadow_log_ready']).lower()}"
    )


def print_text_report(report: dict[str, object]) -> None:
    print_summary(report)
    for command in report["commands"]:
        print(f"STEP {command['step']}: {command['command']}")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
