"""校验生产预检报告中的业务合约证据。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

BUSINESS_CONTRACT_CHECK_KEY = "business_contracts.static_checks"
REQUIRED_CONTRACT_LABELS = (
    "employee_agent_capability_contracts",
    "customer_rag_golden_cases",
    "knowledge_governance_plan",
    "customer_memory_governance_plan",
    "customer_observability_contract",
    "miniapp_page_api_contract",
    "github_reference_implementation_plan",
)


@dataclass(frozen=True)
class PreflightContractEvidenceCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


def load_preflight_report(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8-sig") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError("preflight report must be a JSON object")
    return payload


def validate_preflight_report(
    payload: dict[str, object],
) -> list[PreflightContractEvidenceCheck]:
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return [
            PreflightContractEvidenceCheck(
                "preflight.checks",
                False,
                "checks must be a list",
            )
        ]
    contract_check = _find_contract_check(checks)
    if contract_check is None:
        return [
            PreflightContractEvidenceCheck(
                BUSINESS_CONTRACT_CHECK_KEY,
                False,
                "business contract check missing",
            )
        ]
    return [
        _check_contract_passed(contract_check),
        *_check_required_contract_labels(contract_check),
    ]


def _find_contract_check(checks: list[object]) -> dict[str, object] | None:
    for check in checks:
        if not isinstance(check, dict):
            continue
        if check.get("key") == BUSINESS_CONTRACT_CHECK_KEY:
            return check
    return None


def _check_contract_passed(
    contract_check: dict[str, object],
) -> PreflightContractEvidenceCheck:
    is_passed = contract_check.get("passed") is True
    return PreflightContractEvidenceCheck(
        BUSINESS_CONTRACT_CHECK_KEY,
        is_passed,
        "" if is_passed else "business contract check is not passed",
    )


def _check_required_contract_labels(
    contract_check: dict[str, object],
) -> list[PreflightContractEvidenceCheck]:
    detail = str(contract_check.get("detail", ""))
    return [
        PreflightContractEvidenceCheck(
            f"contract.{label}",
            f"{label}:passed" in detail,
            "" if f"{label}:passed" in detail else "required passed label missing",
        )
        for label in REQUIRED_CONTRACT_LABELS
    ]


def build_json_report(
    checks: list[PreflightContractEvidenceCheck],
    report_path: Path,
) -> dict[str, object]:
    failed_checks = [check for check in checks if not check.passed]
    return {
        "status": "passed" if not failed_checks else "failed",
        "metadata": {
            "generated_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "preflight_report": str(report_path),
        },
        "total": len(checks),
        "failed": len(failed_checks),
        "checks": [check.to_dict() for check in checks],
        "failed_names": [check.name for check in failed_checks],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check business contract evidence in a preflight JSON report"
    )
    parser.add_argument("report_path", help="preflight_production.py --json 输出文件")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report_path = Path(args.report_path)
    try:
        checks = validate_preflight_report(load_preflight_report(report_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"读取预检报告失败: {exc}", file=sys.stderr)
        return 2
    report = build_json_report(checks, report_path)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "preflight_business_contracts "
            f"status={report['status']} total={report['total']} failed={report['failed']}"
        )
    else:
        print(f"preflight_business_contracts status={report['status']}")
        for check in checks:
            mark = "OK" if check.passed else "FAIL"
            print(f"[{mark}] {check.name} {check.detail}".rstrip())
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
