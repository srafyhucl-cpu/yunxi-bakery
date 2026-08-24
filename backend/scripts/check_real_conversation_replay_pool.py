"""脱敏真实会话 replay 样本池准入检查。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

DEFAULT_POOL_MANIFEST_PATH = (
    ROOT_DIR / "tests" / "fixtures" / "customer_real_replay_pool_manifest_sample.json"
)
REAL_ENTRY_REQUIRED_TEXT_FIELDS = (
    "source_type",
    "redaction_method",
    "redaction_reviewer",
    "redaction_reviewed_at",
    "raw_source_retention",
)
REAL_SOURCE_TYPE = "real_customer_conversation"
RAW_SOURCE_RETENTION_NOT_COMMITTED = "not_committed"
SYNTHETIC_SOURCE_MARKERS = ("synthetic", "schema_sample", "contract_shape_only")


def build_real_replay_pool_report(
    *,
    manifest_path: Path = DEFAULT_POOL_MANIFEST_PATH,
    require_real: bool = False,
) -> dict[str, object]:
    manifest = load_json_object(manifest_path)
    entries = extract_entries(manifest)
    entry_reports = [
        build_entry_report(entry, manifest_path=manifest_path) for entry in entries
    ]
    failed = sum(1 for entry in entry_reports if entry["status"] == "failed")
    real_entries = [
        entry
        for entry in entry_reports
        if entry["is_real_customer_data"] is True and entry["status"] == "passed"
    ]
    if require_real and not real_entries:
        failed += 1
    real_pool_ready = failed == 0 and bool(real_entries)
    return {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "manifest": str(manifest_path),
        "source": metadata_text(manifest, "source"),
        "contains_real_customer_data": metadata_bool(
            manifest, "contains_real_customer_data"
        ),
        "require_real": require_real,
        "real_pool_ready": real_pool_ready,
        "total": len(entry_reports),
        "failed": failed,
        "real_entries": len(real_entries),
        "synthetic_entries": sum(
            1 for entry in entry_reports if entry["is_real_customer_data"] is False
        ),
        "entries": entry_reports,
    }


def build_entry_report(
    entry: dict[str, Any],
    *,
    manifest_path: Path,
) -> dict[str, object]:
    name = str(entry.get("name", "")).strip()
    enabled = entry.get("enabled") is True
    is_real_customer_data = entry.get("is_real_customer_data") is True
    min_per_scenario = int(entry.get("min_per_scenario") or DEFAULT_MIN_PER_SCENARIO)
    fixture_path = resolve_manifest_path(
        manifest_path=manifest_path,
        raw_path=str(entry.get("fixture", "")).strip(),
    )
    assertions = {
        "name.present": bool(name),
        "fixture.present": bool(str(entry.get("fixture", "")).strip()),
        "enabled.boolean": isinstance(entry.get("enabled"), bool),
        "is_real_customer_data.boolean": isinstance(
            entry.get("is_real_customer_data"), bool
        ),
        "evidence_id.present": bool(str(entry.get("evidence_id", "")).strip()),
    }
    if not enabled:
        return {
            "name": name,
            "fixture": str(fixture_path),
            "status": "skipped",
            "enabled": enabled,
            "is_real_customer_data": is_real_customer_data,
            "purpose": str(entry.get("purpose", "")),
            "min_per_scenario": min_per_scenario,
            "evidence_id": str(entry.get("evidence_id", "")),
            "assertions": assertions,
        }
    assertions["fixture.exists"] = fixture_path.exists()
    fixture_payload = load_json_object(fixture_path) if fixture_path.exists() else {}
    assertions["fixture.contains_sensitive_data_false"] = (
        metadata_raw_value(fixture_payload, "contains_sensitive_data") is False
    )
    replay_summary = build_missing_replay_summary()
    coverage_summary = build_missing_coverage_summary(min_per_scenario)
    if fixture_path.exists():
        replay_result = build_real_conversation_replay_result(
            replay_fixture_path=fixture_path
        )
        replay_summary = {
            "status": replay_result.status,
            "total": replay_result.total,
            "failed": replay_result.failed,
            "pass_rate": replay_result.pass_rate,
        }
        coverage_report = build_real_replay_coverage_report(
            replay_fixture_path=fixture_path,
            min_per_scenario=min_per_scenario,
        )
        coverage_summary = {
            "status": coverage_report["status"],
            "total": coverage_report["total"],
            "failed": coverage_report["failed"],
            "min_per_scenario": coverage_report["min_per_scenario"],
            "replay_total": coverage_report["replay_total"],
        }
        assertions["replay.passed"] = replay_result.status == "passed"
        assertions["coverage.passed"] = coverage_report["status"] == "passed"
    if is_real_customer_data:
        assertions.update(
            build_real_entry_assertions(entry, fixture_payload, manifest_path)
        )
    status = "passed" if all(assertions.values()) else "failed"
    return {
        "name": name,
        "fixture": str(fixture_path),
        "status": status,
        "enabled": enabled,
        "is_real_customer_data": is_real_customer_data,
        "purpose": str(entry.get("purpose", "")),
        "source_type": str(entry.get("source_type", "")),
        "redaction_method": str(entry.get("redaction_method", "")),
        "redaction_reviewer": str(entry.get("redaction_reviewer", "")),
        "redaction_reviewed_at": str(entry.get("redaction_reviewed_at", "")),
        "raw_source_retention": str(entry.get("raw_source_retention", "")),
        "min_per_scenario": min_per_scenario,
        "evidence_id": str(entry.get("evidence_id", "")),
        "assertions": assertions,
        "replay": replay_summary,
        "coverage": coverage_summary,
    }


def build_real_entry_assertions(
    entry: dict[str, Any],
    fixture_payload: dict[str, object],
    manifest_path: Path,
) -> dict[str, bool]:
    return {
        "manifest.contains_real_customer_data_true": manifest_declares_real_customer_data(
            manifest_path
        ),
        "source_type.real_customer_conversation": str(
            entry.get("source_type", "")
        ).strip()
        == REAL_SOURCE_TYPE,
        "redaction_method.present": bool(
            str(entry.get("redaction_method", "")).strip()
        ),
        "redaction_reviewer.present": bool(
            str(entry.get("redaction_reviewer", "")).strip()
        ),
        "redaction_reviewed_at.present": bool(
            str(entry.get("redaction_reviewed_at", "")).strip()
        ),
        "raw_source_retention.not_committed": str(
            entry.get("raw_source_retention", "")
        ).strip()
        == RAW_SOURCE_RETENTION_NOT_COMMITTED,
        "fixture.source_not_synthetic": not is_synthetic_fixture_source(
            fixture_payload
        ),
        "fixture.redaction.present": bool(metadata_text(fixture_payload, "redaction")),
    }


def manifest_declares_real_customer_data(manifest_path: Path) -> bool:
    manifest_payload = load_json_object(manifest_path)
    return metadata_bool(manifest_payload, "contains_real_customer_data")


def is_synthetic_fixture_source(fixture_payload: dict[str, object]) -> bool:
    source = metadata_text(fixture_payload, "source").lower()
    return any(marker in source for marker in SYNTHETIC_SOURCE_MARKERS)


def build_missing_replay_summary() -> dict[str, object]:
    return {"status": "missing", "total": 0, "failed": 0, "pass_rate": 0.0}


def build_missing_coverage_summary(min_per_scenario: int) -> dict[str, object]:
    return {
        "status": "missing",
        "total": 0,
        "failed": 0,
        "min_per_scenario": min_per_scenario,
        "replay_total": 0,
    }


def load_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {}


def extract_entries(manifest: dict[str, object]) -> list[dict[str, Any]]:
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def resolve_manifest_path(*, manifest_path: Path, raw_path: str) -> Path:
    if not raw_path:
        return Path("")
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    manifest_relative = manifest_path.parent / candidate
    if manifest_relative.exists():
        return manifest_relative
    return ROOT_DIR / candidate


def metadata_text(payload: dict[str, object], key: str) -> str:
    value = metadata_raw_value(payload, key)
    return str(value) if value is not None else ""


def metadata_bool(payload: dict[str, object], key: str) -> bool:
    return metadata_raw_value(payload, key) is True


def metadata_raw_value(payload: dict[str, object], key: str) -> object:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return None
    return metadata.get(key)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check sanitized real conversation replay pool manifest"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument("--json-out", type=Path, help="写入 JSON 报告路径")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_POOL_MANIFEST_PATH,
        help="脱敏真实会话 replay 样本池 manifest",
    )
    parser.add_argument(
        "--require-real",
        action="store_true",
        help="要求至少一个真实脱敏样本池条目通过；合成样例不能满足该门禁",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_real_replay_pool_report(
        manifest_path=args.manifest,
        require_real=args.require_real,
    )
    if args.json_out is not None:
        write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "real_conversation_replay_pool "
            f"status={report['status']} total={report['total']} "
            f"failed={report['failed']} real_entries={report['real_entries']} "
            f"real_ready={str(report['real_pool_ready']).lower()}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_text_report(report: dict[str, object]) -> None:
    print("real_conversation_replay_pool")
    print(
        f"status={report['status']} total={report['total']} "
        f"failed={report['failed']} real_ready={report['real_pool_ready']}"
    )
    for entry in report["entries"]:
        print(
            f"{str(entry['status']).upper()} {entry['name']} "
            f"real={entry['is_real_customer_data']}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
