"""RAG 真实检索日志 shadow 观测入口。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from app.service.agents.evaluation import write_json_report  # noqa: E402
from scripts import eval_retrieval  # noqa: E402
from scripts import report_retrieval_eval_matrix as eval_matrix  # noqa: E402
from scripts import report_retrieval_shadow_compare as shadow_compare  # noqa: E402

DEFAULT_DB_PATH = ROOT_DIR / "data" / "bot.db"
DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "retrieval-shadow" / "rag-shadow-log-observability.json"
)
DEFAULT_K = 5
DEFAULT_RERANK_CANDIDATE_MULTIPLIER = eval_retrieval.DEFAULT_RERANK_CANDIDATE_MULTIPLIER
REQUIRED_RECORD_FIELDS = (
    "id",
    "query",
    "baseline_top_keys",
)
REAL_SHADOW_LOG_SOURCE_TYPE = "real_customer_rag_shadow_log"
RAW_SOURCE_RETENTION_NOT_COMMITTED = "not_committed"
REQUIRED_METADATA_FIELDS = (
    "source_type",
    "contains_sensitive_data",
    "redaction_method",
    "redaction_reviewer",
    "redaction_reviewed_at",
    "raw_source_retention",
    "evidence_id",
)
REDACTION_REQUIREMENTS = (
    "input metadata 必须声明 contains_sensitive_data=false",
    "input metadata 必须声明 source_type=real_customer_rag_shadow_log",
    "input metadata 必须包含脱敏方法、审核人、审核日期和 evidence ID",
    "input metadata 必须声明 raw_source_retention=not_committed",
    "query 必须是已脱敏文本，不得包含手机号、地址、open_id、完整订单号或客户姓名",
    "报告默认只输出 query_hash，不输出 query 原文",
    "原始生产日志只能保存在仓库外，不得提交到 git",
)
SENSITIVE_QUERY_PATTERNS = (
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)\d{12,}(?!\d)"),
    re.compile(r"\b(?:o|wm)[A-Za-z0-9_-]{18,}\b", re.IGNORECASE),
)


def build_rag_shadow_log_observability_report(
    *,
    input_path: Path | None = None,
    db_path: Path = DEFAULT_DB_PATH,
    k: int = DEFAULT_K,
    require_input: bool = False,
    include_queries: bool = False,
) -> dict[str, object]:
    if input_path is None:
        return build_missing_input_report(
            require_input=require_input, db_path=db_path, k=k
        )
    payload = load_input_payload(input_path)
    metadata = metadata_object(payload)
    records_value = payload.get("records", [])
    records = list(records_value) if isinstance(records_value, list) else []
    input_assertions = build_input_assertions(payload=payload, records=records)
    if any(not passed for passed in input_assertions.values()):
        return build_invalid_input_report(
            input_path=input_path,
            db_path=db_path,
            k=k,
            input_assertions=input_assertions,
        )
    shadow_records = build_shadow_records(
        records=records,
        db_path=db_path,
        k=k,
    )
    summary = summarize_shadow_records(shadow_records)
    assertions = {
        **input_assertions,
        "shadow_log.records_present": bool(records),
        "shadow_log.candidates_present": all(
            bool(record["candidates"]) for record in shadow_records
        ),
    }
    failed = sum(1 for passed in assertions.values() if not passed)
    report: dict[str, object] = {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "failed": failed,
        "shadow_log_ready": failed == 0,
        "metadata": {
            "input": str(input_path),
            "db": str(db_path),
            "k": k,
            "record_count": len(records),
            "source_type": metadata.get("source_type", ""),
            "redaction_method": metadata.get("redaction_method", ""),
            "redaction_reviewed_at": metadata.get("redaction_reviewed_at", ""),
            "raw_source_retention": metadata.get("raw_source_retention", ""),
            "evidence_id": metadata.get("evidence_id", ""),
        },
        "summary": summary,
        "records": sanitize_shadow_records(
            shadow_records, include_queries=include_queries
        ),
        "assertions": assertions,
        "missing_actions": build_missing_actions(assertions),
        "boundaries": {
            "production_hot_path_changed": False,
            "rag_retrieval_mode_changed": False,
            "external_llm_called": False,
            "business_database_written": False,
            "contains_user_query_text": include_queries,
            "raw_production_log_committed": False,
        },
    }
    return report


def build_missing_input_report(
    *,
    require_input: bool,
    db_path: Path,
    k: int,
) -> dict[str, object]:
    return {
        "status": "failed" if require_input else "passed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "failed": 1 if require_input else 0,
        "shadow_log_ready": False,
        "metadata": {
            "input": "",
            "db": str(db_path),
            "k": k,
            "record_count": 0,
            "source_type": "",
        },
        "required_record_fields": list(REQUIRED_RECORD_FIELDS),
        "required_metadata_fields": list(REQUIRED_METADATA_FIELDS),
        "redaction_requirements": list(REDACTION_REQUIREMENTS),
        "commands": {
            "build_input": (
                "先运行 python scripts\\build_rag_shadow_log_intake_packet.py "
                "--summary，再由日志持有人在仓库外填写模板"
            ),
            "check_input": (
                "python scripts\\report_rag_shadow_log_observability.py "
                "--input reports\\retrieval-shadow\\rag-shadow-log-input.json "
                "--require-input --summary"
            ),
            "strict_gate": (
                "python scripts\\report_rag_shadow_log_observability.py "
                "--input reports\\retrieval-shadow\\rag-shadow-log-input.json "
                "--require-input --summary"
            ),
        },
        "assertions": {
            "shadow_log.input_present": False,
            "shadow_log.input_required": not require_input,
        },
        "missing_actions": ["provide_redacted_rag_shadow_log_input"],
        "boundaries": {
            "production_hot_path_changed": False,
            "rag_retrieval_mode_changed": False,
            "external_llm_called": False,
            "business_database_written": False,
            "contains_user_query_text": False,
            "raw_production_log_committed": False,
        },
    }


def load_input_payload(input_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def metadata_object(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def build_input_assertions(
    *,
    payload: dict[str, Any],
    records: list[Any],
) -> dict[str, bool]:
    metadata = metadata_object(payload)
    return {
        "metadata.contains_sensitive_data_false": metadata.get(
            "contains_sensitive_data"
        )
        is False,
        "metadata.source_type.real_customer_rag_shadow_log": str(
            metadata.get("source_type", "")
        ).strip()
        == REAL_SHADOW_LOG_SOURCE_TYPE,
        "metadata.redaction_method.present": is_completed_metadata_text(
            metadata.get("redaction_method")
        ),
        "metadata.redaction_reviewer.present": is_completed_metadata_text(
            metadata.get("redaction_reviewer")
        ),
        "metadata.redaction_reviewed_at.iso_date": is_iso_date(
            metadata.get("redaction_reviewed_at")
        ),
        "metadata.raw_source_retention.not_committed": str(
            metadata.get("raw_source_retention", "")
        ).strip()
        == RAW_SOURCE_RETENTION_NOT_COMMITTED,
        "metadata.evidence_id.present": is_completed_metadata_text(
            metadata.get("evidence_id")
        ),
        "records.present": bool(records),
        "records.required_fields_present": all(
            isinstance(record, dict)
            and all(
                field in record and record[field] for field in REQUIRED_RECORD_FIELDS
            )
            for record in records
        ),
        "records.baseline_top_keys_list": all(
            isinstance(record.get("baseline_top_keys"), list) for record in records
        )
        if records
        else False,
        "records.no_obvious_sensitive_patterns": all(
            isinstance(record, dict)
            and not contains_obvious_sensitive_query(record.get("query"))
            for record in records
        )
        if records
        else False,
    }


def build_invalid_input_report(
    *,
    input_path: Path,
    db_path: Path,
    k: int,
    input_assertions: dict[str, bool],
) -> dict[str, object]:
    failed = sum(1 for passed in input_assertions.values() if not passed)
    return {
        "status": "failed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "failed": failed,
        "shadow_log_ready": False,
        "metadata": {
            "input": str(input_path),
            "db": str(db_path),
            "k": k,
            "record_count": 0,
            "source_type": "",
        },
        "assertions": input_assertions,
        "missing_actions": build_missing_actions(input_assertions),
        "boundaries": {
            "production_hot_path_changed": False,
            "rag_retrieval_mode_changed": False,
            "external_llm_called": False,
            "business_database_written": False,
            "contains_user_query_text": False,
            "raw_production_log_committed": False,
        },
    }


def build_shadow_records(
    *,
    records: list[Any],
    db_path: Path,
    k: int,
) -> list[dict[str, object]]:
    corpus = eval_retrieval.load_corpus(db_path)
    scenarios = (
        shadow_compare.DEFAULT_BASELINE,
        *shadow_compare.DEFAULT_CANDIDATES,
    )
    indexes = eval_matrix.build_search_indexes(scenarios, corpus)
    searchers = {
        scenario.name: eval_matrix.build_searcher(
            scenario,
            indexes,
            corpus,
            rerank_candidate_multiplier=DEFAULT_RERANK_CANDIDATE_MULTIPLIER,
        )
        for scenario in scenarios
    }
    return [
        build_shadow_record(record, searchers=searchers, k=k)
        for record in records
        if isinstance(record, dict)
    ]


def build_shadow_record(
    record: dict[str, Any],
    *,
    searchers: dict[str, Any],
    k: int,
) -> dict[str, object]:
    query = str(record["query"])
    baseline_top_keys = [str(key) for key in record.get("baseline_top_keys", [])]
    candidates = []
    for name, searcher in searchers.items():
        top_keys = [key for key, _score in searcher.search(query, limit=k)]
        if name == shadow_compare.DEFAULT_BASELINE.name:
            continue
        candidates.append(
            {
                "name": name,
                "top_keys": top_keys,
                "changed": top_keys != baseline_top_keys,
                "overlap_count": len(set(top_keys) & set(baseline_top_keys)),
            }
        )
    return {
        "id": str(record["id"]),
        "group": str(record.get("group", "ungrouped") or "ungrouped"),
        "query": query,
        "query_hash": hash_query(query),
        "baseline": {
            "name": shadow_compare.DEFAULT_BASELINE.name,
            "top_keys": baseline_top_keys,
        },
        "candidates": candidates,
    }


def sanitize_shadow_records(
    records: list[dict[str, object]],
    *,
    include_queries: bool,
) -> list[dict[str, object]]:
    sanitized = []
    for record in records:
        item = {key: value for key, value in record.items() if key != "query"}
        if include_queries:
            item["query"] = record["query"]
        sanitized.append(item)
    return sanitized


def summarize_shadow_records(records: list[dict[str, object]]) -> dict[str, object]:
    changed_by_candidate: dict[str, int] = {}
    changed_by_group: dict[str, int] = {}
    for record in records:
        group = str(record["group"])
        if any(candidate["changed"] for candidate in record["candidates"]):
            changed_by_group[group] = changed_by_group.get(group, 0) + 1
        for candidate in record["candidates"]:
            if candidate["changed"]:
                name = str(candidate["name"])
                changed_by_candidate[name] = changed_by_candidate.get(name, 0) + 1
    return {
        "total_records": len(records),
        "changed_by_candidate": changed_by_candidate,
        "changed_by_group": changed_by_group,
    }


def build_missing_actions(assertions: dict[str, bool]) -> list[str]:
    actions = []
    if not assertions.get("metadata.contains_sensitive_data_false", True):
        actions.append("mark_shadow_log_input_as_desensitized")
    if not assertions.get("records.present", True):
        actions.append("provide_redacted_rag_shadow_log_input")
    if not assertions.get("records.required_fields_present", True):
        actions.append("fix_shadow_log_input_required_fields")
    if not assertions.get("records.baseline_top_keys_list", True):
        actions.append("fix_shadow_log_input_baseline_top_keys")
    if not assertions.get("records.no_obvious_sensitive_patterns", True):
        actions.append("redact_shadow_log_query_sensitive_patterns")
    if not assertions.get("metadata.source_type.real_customer_rag_shadow_log", True):
        actions.append("set_shadow_log_source_type_real_customer_rag_shadow_log")
    if not assertions.get("metadata.redaction_method.present", True):
        actions.append("provide_shadow_log_redaction_method")
    if not assertions.get("metadata.redaction_reviewer.present", True):
        actions.append("provide_shadow_log_redaction_reviewer")
    if not assertions.get("metadata.redaction_reviewed_at.iso_date", True):
        actions.append("provide_shadow_log_redaction_reviewed_at_iso_date")
    if not assertions.get("metadata.raw_source_retention.not_committed", True):
        actions.append("declare_shadow_log_raw_source_not_committed")
    if not assertions.get("metadata.evidence_id.present", True):
        actions.append("provide_shadow_log_evidence_id")
    if not assertions.get("shadow_log.candidates_present", True):
        actions.append("rerun_shadow_candidates_for_log_input")
    return actions


def hash_query(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


def contains_obvious_sensitive_query(value: object) -> bool:
    query = str(value or "")
    return any(pattern.search(query) for pattern in SENSITIVE_QUERY_PATTERNS)


def is_completed_metadata_text(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and not (text.startswith("<") and text.endswith(">"))


def is_iso_date(value: object) -> bool:
    if not is_completed_metadata_text(value):
        return False
    try:
        date.fromisoformat(str(value).strip())
    except ValueError:
        return False
    return True


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build RAG shadow log observability")
    parser.add_argument("--input", type=Path, help="脱敏 RAG shadow log input JSON")
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite 语料库"
    )
    parser.add_argument("--k", type=int, default=DEFAULT_K, help="Top-K 截断")
    parser.add_argument(
        "--require-input",
        action="store_true",
        help="要求提供真实脱敏 shadow log input",
    )
    parser.add_argument(
        "--include-queries",
        action="store_true",
        help="显式输出脱敏 query 文本；默认只输出 query_hash",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="写入 RAG shadow log 观测 JSON 路径",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if not args.db.exists():
        print(f"[ERROR] 语料库不存在: {args.db}", file=sys.stderr)
        return 1
    report = build_rag_shadow_log_observability_report(
        input_path=args.input,
        db_path=args.db,
        k=args.k,
        require_input=args.require_input,
        include_queries=args.include_queries,
    )
    if args.json_out is not None:
        write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "rag_shadow_log_observability "
            f"status={report['status']} failed={report['failed']} "
            f"shadow_log_ready={str(report['shadow_log_ready']).lower()}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_text_report(report: dict[str, object]) -> None:
    print("rag_shadow_log_observability")
    print(
        f"status={report['status']} failed={report['failed']} "
        f"shadow_log_ready={str(report['shadow_log_ready']).lower()}"
    )
    for action in report["missing_actions"]:
        print(f"NEXT {action}")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
