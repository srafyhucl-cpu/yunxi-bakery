"""客户长期记忆治理计划静态验收。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PLAN_PATH = ROOT_DIR / "docs" / "architecture" / "customer-memory-governance-plan.md"
REQUIRED_TERMS = (
    "customer_profiles",
    "conversation_summaries",
    "MemoryAgent",
    "customer_memory.py",
    "profile_prompt.py",
    "source_evidence_json",
    "consent_status",
    "unknown / granted / revoked",
    "confidence",
    "status",
    "expires_at",
    "last_verified_at",
    "withdrawn_at",
    "session_scope",
    "bot_then_handoff_partial",
    "过敏原",
    "特殊日期",
    "撤销",
    "过期",
)
REQUIRED_BOUNDARIES = (
    "不能直接写入长期画像",
    "不能作为事实结论",
    "长期记忆只允许冷路径写入",
    "不能从会话摘要直接提升",
    "读取失败必须空画像降级",
    "consent_status=revoked",
)
FORBIDDEN_DIRECTIVES = (
    "把会话摘要直接写入 `customer_profiles`",
    "热路径直接写 `customer_profiles`",
    "长期记忆作为订单事实来源",
)


@dataclass(frozen=True)
class PlanCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


def load_plan(path: Path = PLAN_PATH) -> str:
    return path.read_text(encoding="utf-8")


def validate_plan(content: str) -> list[PlanCheck]:
    has_content = bool(content.strip())
    return [
        PlanCheck("plan.exists", has_content, "" if has_content else "plan is empty"),
        *_check_required_terms(content),
        *_check_required_boundaries(content),
        *_check_forbidden_directives(content),
        _check_no_placeholders(content),
    ]


def _check_required_terms(content: str) -> list[PlanCheck]:
    return [
        PlanCheck(
            f"required.{term}",
            term in content,
            "" if term in content else "required memory governance term missing",
        )
        for term in REQUIRED_TERMS
    ]


def _check_required_boundaries(content: str) -> list[PlanCheck]:
    return [
        PlanCheck(
            f"boundary.{term}",
            term in content,
            "" if term in content else "required memory boundary missing",
        )
        for term in REQUIRED_BOUNDARIES
    ]


def _check_forbidden_directives(content: str) -> list[PlanCheck]:
    return [
        PlanCheck(
            f"forbidden.{term}",
            term not in content,
            "" if term not in content else "forbidden implementation directive found",
        )
        for term in FORBIDDEN_DIRECTIVES
    ]


def _check_no_placeholders(content: str) -> PlanCheck:
    placeholders = ("TBD", "TODO", "待定", "占位")
    found = [item for item in placeholders if item in content]
    return PlanCheck(
        "plan.no_placeholders",
        not found,
        "" if not found else f"placeholders found: {', '.join(found)}",
    )


def build_json_report(checks: list[PlanCheck]) -> dict[str, object]:
    failed_checks = [check for check in checks if not check.passed]
    return {
        "status": "passed" if not failed_checks else "failed",
        "metadata": {
            "generated_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "plan": str(PLAN_PATH),
        },
        "total": len(checks),
        "failed": len(failed_checks),
        "checks": [check.to_dict() for check in checks],
        "failed_names": [check.name for check in failed_checks],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check customer memory governance plan"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    checks = validate_plan(load_plan())
    report = build_json_report(checks)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "customer_memory_governance_plan "
            f"status={report['status']} total={report['total']} failed={report['failed']}"
        )
    else:
        print(f"customer_memory_governance_plan status={report['status']}")
        for check in checks:
            mark = "OK" if check.passed else "FAIL"
            print(f"[{mark}] {check.name} {check.detail}".rstrip())
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
