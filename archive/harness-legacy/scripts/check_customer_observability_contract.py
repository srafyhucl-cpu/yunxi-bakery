"""客户机器人可观测合约静态验收。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CONTRACT_PATH = (
    ROOT_DIR / "docs" / "architecture" / "customer-observability-contract.md"
)
REQUIRED_METRICS = (
    "knowledge_hit_rate",
    "no_data_fallback_rate",
    "handoff_rate",
    "tool_success_rate",
    "context_pressure_rate",
)
REQUIRED_FIELDS = (
    "trace_id",
    "session_id",
    "channel_type",
    "bot_type",
    "intent",
    "retrieval_status",
    "knowledge_doc_ids",
    "tool_name",
    "tool_status",
    "handoff_reason",
    "fallback_reason",
    "context_budget_tokens",
    "summary_used",
    "latency_ms",
)
REQUIRED_SOURCES = (
    "knowledge_retrieval_logs",
    "RAG golden cases",
    "conversation_summaries",
    "scripts/report_knowledge_retrieval_logs.py",
    "scripts/check_customer_long_context_summary_smoke.py",
    "scripts/preflight_production.py --json",
    "scripts/check_preflight_business_contracts.py",
)
REQUIRED_BOUNDARIES = (
    "不引入 LangChain / LangGraph",
    "不改客户机器人热路径",
    "不改员工助手 planner、工具调用或确定性回复",
    "不记录完整手机号",
    "不记录完整地址",
    "不记录完整订单号",
    "不记录完整交易号",
    "不记录密钥、Token、Cookie",
    "观测失败必须降级为空指标",
    "不能阻断客服回复",
)
FORBIDDEN_DIRECTIVES = (
    "用指标结果自动改写回复",
    "把观测字段当成客户画像",
    "把观测字段当成订单事实",
)


@dataclass(frozen=True)
class ContractCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


def load_contract(path: Path = CONTRACT_PATH) -> str:
    return path.read_text(encoding="utf-8")


def validate_contract(content: str) -> list[ContractCheck]:
    has_content = bool(content.strip())
    return [
        ContractCheck(
            "contract.exists",
            has_content,
            "" if has_content else "contract is empty",
        ),
        *_check_required_items("metric", REQUIRED_METRICS, content),
        *_check_required_items("field", REQUIRED_FIELDS, content),
        *_check_required_items("source", REQUIRED_SOURCES, content),
        *_check_required_items("boundary", REQUIRED_BOUNDARIES, content),
        *_check_forbidden_directives(content),
        _check_no_placeholders(content),
    ]


def _check_required_items(
    prefix: str,
    items: tuple[str, ...],
    content: str,
) -> list[ContractCheck]:
    return [
        ContractCheck(
            f"{prefix}.{item}",
            item in content,
            "" if item in content else f"required {prefix} missing",
        )
        for item in items
    ]


def _check_forbidden_directives(content: str) -> list[ContractCheck]:
    return [
        ContractCheck(
            f"forbidden.{item}",
            item not in content,
            "" if item not in content else "forbidden observability directive found",
        )
        for item in FORBIDDEN_DIRECTIVES
    ]


def _check_no_placeholders(content: str) -> ContractCheck:
    placeholders = ("TBD", "TODO", "待定", "占位")
    found = [item for item in placeholders if item in content]
    return ContractCheck(
        "contract.no_placeholders",
        not found,
        "" if not found else f"placeholders found: {', '.join(found)}",
    )


def build_json_report(checks: list[ContractCheck]) -> dict[str, object]:
    failed_checks = [check for check in checks if not check.passed]
    return {
        "status": "passed" if not failed_checks else "failed",
        "metadata": {
            "generated_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "contract": str(CONTRACT_PATH),
        },
        "total": len(checks),
        "failed": len(failed_checks),
        "checks": [check.to_dict() for check in checks],
        "failed_names": [check.name for check in failed_checks],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check customer observability contract"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    checks = validate_contract(load_contract())
    report = build_json_report(checks)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "customer_observability_contract "
            f"status={report['status']} total={report['total']} failed={report['failed']}"
        )
    else:
        print(f"customer_observability_contract status={report['status']}")
        for check in checks:
            mark = "OK" if check.passed else "FAIL"
            print(f"[{mark}] {check.name} {check.detail}".rstrip())
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
