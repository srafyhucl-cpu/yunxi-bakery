"""生成真实脱敏 replay 样本池条目草稿。"""

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
    ROOT_DIR / "reports" / "agent-eval" / "real-replay-pool-entry-draft.json"
)


def build_pool_entry_draft_report(
    *,
    fixture_path: Path,
    name: str,
    evidence_id: str,
    redaction_method: str,
    redaction_reviewer: str,
    redaction_reviewed_at: str,
    purpose: str = "approved_redacted_regression",
    source_type: str = REAL_SOURCE_TYPE,
    raw_source_retention: str = RAW_SOURCE_RETENTION_NOT_COMMITTED,
    min_per_scenario: int = DEFAULT_MIN_PER_SCENARIO,
) -> dict[str, object]:
    fixture_payload = load_json_object(fixture_path)
    coverage = build_real_replay_coverage_report(
        replay_fixture_path=fixture_path,
        min_per_scenario=min_per_scenario,
    )
    assertions = build_assertions(
        fixture_path=fixture_path,
        fixture_payload=fixture_payload,
        coverage=coverage,
        name=name,
        evidence_id=evidence_id,
        redaction_method=redaction_method,
        redaction_reviewer=redaction_reviewer,
        redaction_reviewed_at=redaction_reviewed_at,
        source_type=source_type,
        raw_source_retention=raw_source_retention,
    )
    entry = build_manifest_entry(
        fixture_path=fixture_path,
        name=name,
        evidence_id=evidence_id,
        redaction_method=redaction_method,
        redaction_reviewer=redaction_reviewer,
        redaction_reviewed_at=redaction_reviewed_at,
        purpose=purpose,
        source_type=source_type,
        raw_source_retention=raw_source_retention,
        min_per_scenario=min_per_scenario,
    )
    failed = sum(1 for passed in assertions.values() if not passed)
    return {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "failed": failed,
        "fixture": str(fixture_path),
        "fixture_metadata": {
            "source": metadata_text(fixture_payload, "source"),
            "redaction": metadata_text(fixture_payload, "redaction"),
            "contains_sensitive_data": metadata_raw_value(
                fixture_payload,
                "contains_sensitive_data",
            ),
        },
        "assertions": assertions,
        "coverage": summarize_coverage(coverage),
        "entry": entry,
        "boundaries": {
            "manifest_modified": False,
            "raw_customer_conversation_read": False,
            "real_customer_data_committed": False,
            "business_database_read": False,
            "external_llm_called": False,
        },
    }


def build_assertions(
    *,
    fixture_path: Path,
    fixture_payload: dict[str, object],
    coverage: dict[str, object],
    name: str,
    evidence_id: str,
    redaction_method: str,
    redaction_reviewer: str,
    redaction_reviewed_at: str,
    source_type: str,
    raw_source_retention: str,
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
        "coverage.passed": coverage.get("status") == "passed",
        "name.present": bool(name.strip()),
        "evidence_id.present": bool(evidence_id.strip()),
        "source_type.real_customer_conversation": source_type.strip()
        == REAL_SOURCE_TYPE,
        "redaction_method.present": bool(redaction_method.strip()),
        "redaction_reviewer.present": bool(redaction_reviewer.strip()),
        "redaction_reviewed_at.present": bool(redaction_reviewed_at.strip()),
        "raw_source_retention.not_committed": raw_source_retention.strip()
        == RAW_SOURCE_RETENTION_NOT_COMMITTED,
    }


def build_manifest_entry(
    *,
    fixture_path: Path,
    name: str,
    evidence_id: str,
    redaction_method: str,
    redaction_reviewer: str,
    redaction_reviewed_at: str,
    purpose: str,
    source_type: str,
    raw_source_retention: str,
    min_per_scenario: int,
) -> dict[str, object]:
    return {
        "name": name,
        "fixture": str(fixture_path),
        "enabled": True,
        "is_real_customer_data": True,
        "purpose": purpose,
        "source_type": source_type,
        "redaction_method": redaction_method,
        "redaction_reviewer": redaction_reviewer,
        "redaction_reviewed_at": redaction_reviewed_at,
        "raw_source_retention": raw_source_retention,
        "min_per_scenario": min_per_scenario,
        "evidence_id": evidence_id,
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


def load_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare real replay pool manifest entry draft"
    )
    parser.add_argument(
        "--fixture", required=True, type=Path, help="脱敏 replay fixture"
    )
    parser.add_argument("--name", required=True, help="样本池条目名称")
    parser.add_argument("--evidence-id", required=True, help="证据索引 ID")
    parser.add_argument("--redaction-method", required=True, help="脱敏方法")
    parser.add_argument("--redaction-reviewer", required=True, help="脱敏审核人")
    parser.add_argument("--redaction-reviewed-at", required=True, help="脱敏审核日期")
    parser.add_argument(
        "--source-type",
        default=REAL_SOURCE_TYPE,
        help="真实样本来源类型",
    )
    parser.add_argument(
        "--raw-source-retention",
        default=RAW_SOURCE_RETENTION_NOT_COMMITTED,
        help="原始来源留存声明",
    )
    parser.add_argument(
        "--purpose",
        default="approved_redacted_regression",
        help="样本池用途说明",
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
        help="写入 entry 草稿报告路径",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_pool_entry_draft_report(
        fixture_path=args.fixture,
        name=args.name,
        evidence_id=args.evidence_id,
        redaction_method=args.redaction_method,
        redaction_reviewer=args.redaction_reviewer,
        redaction_reviewed_at=args.redaction_reviewed_at,
        source_type=args.source_type,
        raw_source_retention=args.raw_source_retention,
        purpose=args.purpose,
        min_per_scenario=args.min_per_scenario,
    )
    if args.json_out is not None:
        write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "real_replay_pool_entry_draft "
            f"status={report['status']} failed={report['failed']} "
            f"coverage={report['coverage']['status']}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_text_report(report: dict[str, object]) -> None:
    print("real_replay_pool_entry_draft")
    print(f"status={report['status']} failed={report['failed']}")
    for name, passed in report["assertions"].items():
        mark = "PASS" if passed else "FAIL"
        print(f"{mark} {name}")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
