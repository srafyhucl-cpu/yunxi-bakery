"""导出脱敏真实会话 replay fixture 草稿。"""

from __future__ import annotations

import argparse
import json
import re
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

DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-conversation-replay-draft.json"
)
PHONE_PATTERN = re.compile(r"1[3-9]\d{9}")
LONG_ID_PATTERN = re.compile(r"\b[A-Z]?\d{14,}\b")
UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
PLATFORM_ID_PATTERN = re.compile(
    r"\b(?:open_id|openid|unionid)[=:：]?[A-Za-z0-9_\-]{0,64}\b",
    re.IGNORECASE,
)
ADDRESS_PATTERN = re.compile(
    r"[\u4e00-\u9fa5]{2,}(?:省|市|区|县|镇|街道|路|号楼|单元|室)[\u4e00-\u9fa5A-Za-z0-9\-#]{0,40}"
)
SENSITIVE_LABEL_REPLACEMENTS = (
    ("手机号", "联系方式"),
    ("电话", "联系方式"),
    ("完整地址", "地址信息"),
    ("收货地址", "地址信息"),
    ("完整订单号", "订单标识"),
    ("open_id", "平台ID"),
    ("openid", "平台ID"),
    ("unionid", "平台ID"),
)


def build_replay_fixture_payload(
    input_path: Path,
    *,
    source: str = "",
    redaction: str = "scripted_redaction_v1",
) -> dict[str, object]:
    records = load_source_records(input_path)
    cases = [
        build_replay_case(record, index=index, source=source or input_path.stem)
        for index, record in enumerate(records, start=1)
    ]
    return {
        "metadata": {
            "source": source or input_path.stem,
            "redaction": redaction,
            "contains_sensitive_data": False,
            "generated_at": generated_at(),
            "app_version": APP_VERSION,
            "input_record_count": len(records),
            "notes": "由导出脚本脱敏生成；写入 gitignored reports 目录后仍需通过 replay checker。",
        },
        "cases": cases,
    }


def load_source_records(input_path: Path) -> list[dict[str, Any]]:
    if input_path.suffix.lower() == ".jsonl":
        return load_jsonl_records(input_path)
    payload = json.loads(input_path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("records", "cases", "conversations", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def load_jsonl_records(input_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in input_path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            records.append(payload)
    return records


def build_replay_case(
    record: dict[str, Any],
    *,
    index: int,
    source: str,
) -> dict[str, object]:
    golden_case_id = first_text(record, "golden_case_id", "golden_id")
    if not golden_case_id:
        raise ValueError(f"第 {index} 条记录缺少 golden_case_id")
    user_message = first_text(
        record,
        "user_message",
        "query",
        "customer_message",
        "message",
        "user_text",
    )
    final_reply = first_text(
        record,
        "final_reply",
        "reply",
        "assistant_reply",
        "bot_reply",
        "answer",
    )
    case_id = first_text(record, "case_id", "id", "conversation_id") or (
        f"real-export-{index:03d}"
    )
    return {
        "case_id": sanitize_identifier(case_id, fallback=f"real-export-{index:03d}"),
        "golden_case_id": golden_case_id,
        "source": sanitize_text(first_text(record, "source") or source),
        "group": sanitize_text(first_text(record, "group")),
        "intent": sanitize_text(first_text(record, "intent")),
        "user_message": sanitize_text(user_message),
        "final_reply": sanitize_text(final_reply),
    }


def first_text(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None:
            return str(value).strip()
    return ""


def sanitize_identifier(value: str, *, fallback: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.:-]+", "-", sanitize_text(value)).strip("-")
    return sanitized or fallback


def sanitize_text(value: str) -> str:
    clean_value = str(value or "")
    clean_value = UUID_PATTERN.sub("[UUID已脱敏]", clean_value)
    clean_value = PLATFORM_ID_PATTERN.sub("[平台ID已脱敏]", clean_value)
    clean_value = PHONE_PATTERN.sub("[联系方式已脱敏]", clean_value)
    clean_value = LONG_ID_PATTERN.sub("[订单标识已脱敏]", clean_value)
    clean_value = ADDRESS_PATTERN.sub("[地址信息已脱敏]", clean_value)
    for old, new in SENSITIVE_LABEL_REPLACEMENTS:
        clean_value = clean_value.replace(old, new)
    return clean_value.strip()


def validate_exported_fixture(output_path: Path) -> dict[str, object]:
    result = build_real_conversation_replay_result(replay_fixture_path=output_path)
    return result.to_dict()


def generated_at() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export sanitized real conversation replay fixture draft"
    )
    parser.add_argument(
        "--input", required=True, type=Path, help="原始 JSON/JSONL 记录"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="写入脱敏 replay fixture 草稿路径",
    )
    parser.add_argument("--source", default="", help="覆盖输出 metadata.source")
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="只导出，不调用 replay checker；默认会校验输出",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 摘要")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    payload = build_replay_fixture_payload(args.input, source=args.source)
    write_json_report(payload, args.output)
    validation = (
        {"status": "skipped", "total": len(payload["cases"]), "failed": 0}
        if args.skip_validation
        else validate_exported_fixture(args.output)
    )
    report = {
        "status": validation.get("status", "missing"),
        "generated_at": generated_at(),
        "input": str(args.input),
        "output": str(args.output),
        "total": validation.get("total", 0),
        "failed": validation.get("failed", 0),
        "validation": validation,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "real_conversation_replay_export "
            f"status={report['status']} total={report['total']} "
            f"failed={report['failed']} output={args.output}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] in {"passed", "skipped"} else 1


def print_text_report(report: dict[str, object]) -> None:
    print("real_conversation_replay_export")
    print(
        f"status={report['status']} total={report['total']} failed={report['failed']}"
    )
    print(f"output={report['output']}")


if __name__ == "__main__":
    raise SystemExit(main())
