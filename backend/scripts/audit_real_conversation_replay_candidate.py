"""真实脱敏 replay 候选样本准入审计。"""

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
from scripts.check_real_conversation_replay import (  # noqa: E402
    build_real_conversation_replay_result,
)
from scripts.check_real_conversation_replay_coverage import (  # noqa: E402
    DEFAULT_MIN_PER_SCENARIO,
    build_real_replay_coverage_report,
)
from scripts.check_real_conversation_replay_pool import (  # noqa: E402
    RAW_SOURCE_RETENTION_NOT_COMMITTED,
    REAL_SOURCE_TYPE,
    SYNTHETIC_SOURCE_MARKERS,
    metadata_raw_value,
    metadata_text,
)

DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-replay-candidate-audit.json"
)


def build_real_replay_candidate_audit_report(
    *,
    fixture_path: Path | None = None,
    require_fixture: bool = False,
    source_type: str = "",
    redaction_method: str = "",
    redaction_reviewer: str = "",
    redaction_reviewed_at: str = "",
    raw_source_retention: str = "",
    evidence_id: str = "",
    name: str = "real_replay_candidate",
    min_per_scenario: int = DEFAULT_MIN_PER_SCENARIO,
) -> dict[str, object]:
    if fixture_path is None:
        return build_missing_fixture_report(require_fixture=require_fixture)

    fixture_payload = load_json_object(fixture_path)
    replay_summary = build_missing_replay_summary()
    coverage_summary = build_missing_coverage_summary(min_per_scenario)
    if fixture_path.exists():
        replay_result = build_real_conversation_replay_result(
            replay_fixture_path=fixture_path
        )
        replay_summary = summarize_replay(replay_result)
        coverage_report = build_real_replay_coverage_report(
            replay_fixture_path=fixture_path,
            min_per_scenario=min_per_scenario,
        )
        coverage_summary = summarize_coverage(coverage_report)

    assertions = build_candidate_assertions(
        fixture_path=fixture_path,
        fixture_payload=fixture_payload,
        replay_summary=replay_summary,
        coverage_summary=coverage_summary,
        source_type=source_type,
        redaction_method=redaction_method,
        redaction_reviewer=redaction_reviewer,
        redaction_reviewed_at=redaction_reviewed_at,
        raw_source_retention=raw_source_retention,
        evidence_id=evidence_id,
    )
    failed = sum(1 for passed in assertions.values() if not passed)
    candidate_ready = failed == 0
    return {
        "status": "passed" if candidate_ready else "failed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "candidate_ready": candidate_ready,
        "fixture": str(fixture_path),
        "failed": failed,
        "missing_actions": build_missing_actions(assertions),
        "fixture_metadata": {
            "source": metadata_text(fixture_payload, "source"),
            "redaction": metadata_text(fixture_payload, "redaction"),
            "contains_sensitive_data": metadata_raw_value(
                fixture_payload,
                "contains_sensitive_data",
            ),
        },
        "assertions": assertions,
        "replay": replay_summary,
        "coverage": coverage_summary,
        "manifest_entry_draft": build_manifest_entry_draft(
            fixture_path=fixture_path,
            name=name,
            evidence_id=evidence_id,
            redaction_method=redaction_method,
            redaction_reviewer=redaction_reviewer,
            redaction_reviewed_at=redaction_reviewed_at,
            source_type=source_type,
            raw_source_retention=raw_source_retention,
            min_per_scenario=min_per_scenario,
        ),
        "boundaries": build_boundaries(),
    }


def build_missing_fixture_report(*, require_fixture: bool) -> dict[str, object]:
    return {
        "status": "failed" if require_fixture else "passed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "candidate_ready": False,
        "fixture": "",
        "failed": 1 if require_fixture else 0,
        "missing_actions": ["provide_redacted_real_replay_candidate_fixture"],
        "fixture_metadata": {
            "source": "",
            "redaction": "",
            "contains_sensitive_data": None,
        },
        "assertions": {"candidate.fixture_present": False},
        "replay": build_missing_replay_summary(),
        "coverage": build_missing_coverage_summary(DEFAULT_MIN_PER_SCENARIO),
        "manifest_entry_draft": {},
        "boundaries": build_boundaries(),
    }


def build_candidate_assertions(
    *,
    fixture_path: Path,
    fixture_payload: dict[str, object],
    replay_summary: dict[str, object],
    coverage_summary: dict[str, object],
    source_type: str,
    redaction_method: str,
    redaction_reviewer: str,
    redaction_reviewed_at: str,
    raw_source_retention: str,
    evidence_id: str,
) -> dict[str, bool]:
    source = metadata_text(fixture_payload, "source").lower()
    return {
        "fixture.exists": fixture_path.exists(),
        "fixture.contains_sensitive_data_false": metadata_raw_value(
            fixture_payload,
            "contains_sensitive_data",
        )
        is False,
        "fixture.redaction.present": bool(metadata_text(fixture_payload, "redaction")),
        "fixture.source_not_synthetic": not any(
            marker in source for marker in SYNTHETIC_SOURCE_MARKERS
        ),
        "replay.passed": replay_summary["status"] == "passed",
        "coverage.passed": coverage_summary["status"] == "passed",
        "source_type.real_customer_conversation": source_type.strip()
        == REAL_SOURCE_TYPE,
        "redaction_method.present": bool(redaction_method.strip()),
        "redaction_reviewer.present": bool(redaction_reviewer.strip()),
        "redaction_reviewed_at.present": bool(redaction_reviewed_at.strip()),
        "raw_source_retention.not_committed": raw_source_retention.strip()
        == RAW_SOURCE_RETENTION_NOT_COMMITTED,
        "evidence_id.present": bool(evidence_id.strip()),
    }


def build_missing_actions(assertions: dict[str, bool]) -> list[str]:
    action_by_assertion = {
        "fixture.exists": "provide_existing_redacted_candidate_fixture",
        "fixture.contains_sensitive_data_false": "mark_candidate_as_desensitized",
        "fixture.redaction.present": "provide_candidate_redaction_metadata",
        "fixture.source_not_synthetic": "provide_non_synthetic_real_candidate_source",
        "replay.passed": "fix_candidate_replay_contract_failures",
        "coverage.passed": "provide_required_sensitive_scenario_coverage",
        "source_type.real_customer_conversation": "set_source_type_real_customer_conversation",
        "redaction_method.present": "provide_redaction_method",
        "redaction_reviewer.present": "provide_redaction_reviewer",
        "redaction_reviewed_at.present": "provide_redaction_reviewed_at",
        "raw_source_retention.not_committed": "declare_raw_source_not_committed",
        "evidence_id.present": "provide_evidence_id",
    }
    return [
        action
        for assertion, action in action_by_assertion.items()
        if assertions.get(assertion) is False
    ]


def build_manifest_entry_draft(
    *,
    fixture_path: Path,
    name: str,
    evidence_id: str,
    redaction_method: str,
    redaction_reviewer: str,
    redaction_reviewed_at: str,
    source_type: str,
    raw_source_retention: str,
    min_per_scenario: int,
) -> dict[str, object]:
    return {
        "name": name,
        "fixture": str(fixture_path),
        "enabled": True,
        "is_real_customer_data": True,
        "purpose": "approved_redacted_regression",
        "source_type": source_type,
        "redaction_method": redaction_method,
        "redaction_reviewer": redaction_reviewer,
        "redaction_reviewed_at": redaction_reviewed_at,
        "raw_source_retention": raw_source_retention,
        "min_per_scenario": min_per_scenario,
        "evidence_id": evidence_id,
    }


def summarize_replay(result: object) -> dict[str, object]:
    return {
        "status": result.status,
        "total": result.total,
        "failed": result.failed,
        "pass_rate": result.pass_rate,
    }


def summarize_coverage(report: dict[str, object]) -> dict[str, object]:
    return {
        "status": report.get("status", "missing"),
        "total": report.get("total", 0),
        "failed": report.get("failed", 0),
        "min_per_scenario": report.get("min_per_scenario", 0),
        "replay_total": report.get("replay_total", 0),
        "replay_failed": report.get("replay_failed", 0),
    }


def build_missing_replay_summary() -> dict[str, object]:
    return {"status": "missing", "total": 0, "failed": 0, "pass_rate": 0.0}


def build_missing_coverage_summary(min_per_scenario: int) -> dict[str, object]:
    return {
        "status": "missing",
        "total": 0,
        "failed": 0,
        "min_per_scenario": min_per_scenario,
        "replay_total": 0,
        "replay_failed": 0,
    }


def build_boundaries() -> dict[str, bool]:
    return {
        "manifest_modified": False,
        "raw_customer_conversation_read": False,
        "real_customer_data_committed": False,
        "business_database_read": False,
        "external_llm_called": False,
    }


def load_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit redacted real conversation replay candidate fixture"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument("--json-out", type=Path, help="写入 JSON 报告路径")
    parser.add_argument("--fixture", type=Path, help="候选脱敏 replay fixture")
    parser.add_argument(
        "--require-fixture",
        action="store_true",
        help="要求显式提供候选 fixture；缺失时失败",
    )
    parser.add_argument("--name", default="real_replay_candidate", help="候选条目名称")
    parser.add_argument(
        "--source-type",
        default="",
        help="真实候选来源类型，必须为 real_customer_conversation",
    )
    parser.add_argument("--redaction-method", default="", help="脱敏方法")
    parser.add_argument("--redaction-reviewer", default="", help="脱敏审核人")
    parser.add_argument("--redaction-reviewed-at", default="", help="脱敏审核日期")
    parser.add_argument(
        "--raw-source-retention",
        default="",
        help="原始来源留存声明，必须为 not_committed",
    )
    parser.add_argument("--evidence-id", default="", help="证据索引 ID")
    parser.add_argument(
        "--min-per-scenario",
        type=int,
        default=DEFAULT_MIN_PER_SCENARIO,
        help="每个事实敏感场景最少样本数",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_real_replay_candidate_audit_report(
        fixture_path=args.fixture,
        require_fixture=args.require_fixture,
        source_type=args.source_type,
        redaction_method=args.redaction_method,
        redaction_reviewer=args.redaction_reviewer,
        redaction_reviewed_at=args.redaction_reviewed_at,
        raw_source_retention=args.raw_source_retention,
        evidence_id=args.evidence_id,
        name=args.name,
        min_per_scenario=args.min_per_scenario,
    )
    if args.json_out is not None:
        write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "real_conversation_replay_candidate_audit "
            f"status={report['status']} "
            f"candidate_ready={str(report['candidate_ready']).lower()} "
            f"failed={report['failed']}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_text_report(report: dict[str, object]) -> None:
    print("real_conversation_replay_candidate_audit")
    print(
        f"status={report['status']} "
        f"candidate_ready={report['candidate_ready']} failed={report['failed']}"
    )
    for name, passed in report["assertions"].items():
        mark = "PASS" if passed else "FAIL"
        print(f"{mark} {name}")


if __name__ == "__main__":
    raise SystemExit(main())
