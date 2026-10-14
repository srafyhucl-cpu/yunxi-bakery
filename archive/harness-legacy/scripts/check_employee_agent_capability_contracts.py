"""企微员工助手能力合约静态检查。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from app.service.wecom.employee_agent_capability_contracts import (  # noqa: E402
    CAPABILITY_CONTRACTS,
    capability_card_names,
)
from scripts.wecom_employee_agent_probe_cases import default_probe_cases  # noqa: E402


@dataclass(frozen=True)
class CapabilityContractCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
        }


def run_checks(check_date: date | None = None) -> list[CapabilityContractCheck]:
    probes = default_probe_cases(check_date or date.today())
    probe_names = {probe.name for probe in probes}
    expected_tools = {tool for probe in probes for tool in probe.expected_tools}
    card_names = capability_card_names()
    contract_names = {contract.name for contract in CAPABILITY_CONTRACTS}
    checks = [
        _set_check("contracts.cover_all_cards", card_names, contract_names),
        _set_check("contracts.no_extra_cards", contract_names, card_names),
        _set_check("probes.cover_all_expected_tools", expected_tools, card_names),
    ]
    for contract in CAPABILITY_CONTRACTS:
        checks.extend(_validate_contract(contract.name, contract, probe_names, probes))
    return checks


def _set_check(
    name: str,
    expected_values: set[str],
    actual_values: set[str],
) -> CapabilityContractCheck:
    missing = sorted(expected_values - actual_values)
    return CapabilityContractCheck(
        name,
        not missing,
        f"missing={missing}" if missing else "",
    )


def _validate_contract(
    name: str,
    contract: object,
    probe_names: set[str],
    probes: tuple[object, ...],
) -> list[CapabilityContractCheck]:
    listed_probes = set(getattr(contract, "probe_names"))
    unknown_probes = sorted(listed_probes - probe_names)
    wrong_tool_probes = sorted(
        probe.name
        for probe in probes
        if probe.name in listed_probes and name not in probe.expected_tools
    )
    return [
        _non_empty_check(f"{name}.parameter_rules", contract.parameter_rules),
        _non_empty_check(
            f"{name}.missing_parameter_reply", contract.missing_parameter_reply
        ),
        _non_empty_check(f"{name}.empty_result_reply", contract.empty_result_reply),
        _non_empty_check(f"{name}.error_reply", contract.error_reply),
        _non_empty_check(f"{name}.probe_names", contract.probe_names),
        CapabilityContractCheck(
            f"{name}.probe_names_exist",
            not unknown_probes,
            f"unknown={unknown_probes}" if unknown_probes else "",
        ),
        CapabilityContractCheck(
            f"{name}.probe_names_match_tool",
            not wrong_tool_probes,
            f"wrong_tool={wrong_tool_probes}" if wrong_tool_probes else "",
        ),
    ]


def _non_empty_check(name: str, value: object) -> CapabilityContractCheck:
    has_value = bool(value)
    return CapabilityContractCheck(
        name,
        has_value,
        "" if has_value else "empty",
    )


def build_json_report(checks: list[CapabilityContractCheck]) -> dict[str, object]:
    failed_checks = [check for check in checks if not check.passed]
    return {
        "status": "passed" if not failed_checks else "failed",
        "metadata": {
            "project_root": str(ROOT_DIR),
            "app_version": APP_VERSION,
            "llm": "disabled",
        },
        "total": len(checks),
        "failed": len(failed_checks),
        "failed_names": [check.name for check in failed_checks],
        "checks": [check.to_dict() for check in checks],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    args = parser.parse_args(argv)
    report = build_json_report(run_checks())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "[employee-agent-capability-contracts] "
            f"{report['status']} total={report['total']} failed={report['failed']}"
        )
    else:
        print(f"[employee-agent-capability-contracts] {report['status']}")
        print(f"total={report['total']} failed={report['failed']}")
        for check in report["checks"]:
            marker = "PASS" if check["passed"] else "FAIL"
            detail = f" {check['detail']}" if check["detail"] else ""
            print(f"{marker} {check['name']}{detail}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
