"""客户机器人 RAG golden cases 结构验收。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT_DIR / "tests" / "fixtures" / "customer_rag_golden_cases.json"
REQUIRED_GROUPS = (
    "product_consultation",
    "inventory",
    "delivery",
    "refund_after_sales",
    "human_transfer",
    "knowledge_no_match",
)
REQUIRED_SENSITIVE_SCENARIOS = (
    "order",
    "refund",
    "after_sales",
    "inventory",
    "price",
    "human_transfer",
)
MIN_SENSITIVE_CASES_PER_SCENARIO = 5
REQUIRED_CASE_FIELDS = ("id", "group", "query", "intent", "relevant", "guardrails")
SENSITIVE_SCENARIO_POLICY_KEYWORDS = {
    "order": (
        ("订单",),
        ("不能编造", "工具", "人工", "订单状态", "确认", "转人工"),
    ),
    "refund": (
        ("退款",),
        ("不能承诺", "订单状态", "制作", "人工", "支付平台", "确认"),
    ),
    "after_sales": (
        ("售后", "照片", "订单", "食品安全", "投诉", "停止食用"),
        ("不能", "必须", "转人工", "收集", "核对", "建议"),
    ),
    "inventory": (
        ("库存", "有货", "下架", "预留", "备货"),
        ("实时", "不能承诺", "门店", "人工", "确认为准", "确认"),
    ),
    "price": (
        ("价格", "报价", "优惠", "配送费", "最低价", "运费"),
        ("不能", "必须", "实时", "知识库", "人工", "规则"),
    ),
    "human_transfer": (
        ("人工", "转人工", "真人"),
        ("必须", "应", "明确", "不能", "需要"),
    ),
}
SENSITIVE_SCENARIO_FORBIDDEN_REPLY_PATTERNS = {
    "order": (
        "已为您查到订单",
        "订单正在制作",
        "订单已经发货",
        "可以直接改订单",
    ),
    "refund": (
        "可以全额退款",
        "马上退款",
        "一定退款",
        "退款多久到账一定是",
    ),
    "after_sales": (
        "一定赔偿",
        "一定补发",
        "责任在我们",
        "可以继续食用",
    ),
    "inventory": (
        "一定有货",
        "保证有货",
        "已经帮您预留",
        "下架商品可以做",
    ),
    "price": (
        "给您最低价",
        "可以免配送费",
        "直接给您优惠",
        "定制价格就是",
    ),
    "human_transfer": (
        "不需要人工",
        "无需转人工",
        "我可以直接处理",
        "不用客服确认",
    ),
}


@dataclass(frozen=True)
class GoldenCaseCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_fixture(payload: dict[str, object]) -> list[GoldenCaseCheck]:
    cases = payload.get("cases")
    if not isinstance(cases, list):
        return [GoldenCaseCheck("fixture.cases", False, "cases must be a list")]

    checks = [_check_meta(payload), *_check_cases(cases)]
    groups = {
        str(case.get("group", ""))
        for case in cases
        if isinstance(case, dict) and case.get("group")
    }
    checks.extend(_check_required_groups(groups))
    checks.extend(_check_sensitive_scenarios(cases))
    checks.extend(_check_sensitive_output_policies())
    return checks


def _check_meta(payload: dict[str, object]) -> GoldenCaseCheck:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return GoldenCaseCheck("fixture.meta", False, "meta must be an object")
    if not meta.get("version") or not meta.get("purpose"):
        return GoldenCaseCheck("fixture.meta", False, "version and purpose required")
    return GoldenCaseCheck("fixture.meta", True)


def _check_cases(cases: list[object]) -> list[GoldenCaseCheck]:
    checks: list[GoldenCaseCheck] = []
    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        checks.append(_check_case(index, case, seen_ids))
        if isinstance(case, dict):
            checks.extend(build_sensitive_policy_checks(case))
    return checks


def _check_case(index: int, case: object, seen_ids: set[str]) -> GoldenCaseCheck:
    name = f"case.{index}"
    if not isinstance(case, dict):
        return GoldenCaseCheck(name, False, "case must be an object")
    missing = [field for field in REQUIRED_CASE_FIELDS if field not in case]
    if missing:
        return GoldenCaseCheck(name, False, f"missing fields: {', '.join(missing)}")
    case_id = str(case["id"])
    if case_id in seen_ids:
        return GoldenCaseCheck(case_id, False, "duplicate id")
    seen_ids.add(case_id)
    errors = _case_content_errors(case)
    return GoldenCaseCheck(case_id, not errors, "; ".join(errors))


def _case_content_errors(case: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for field in ("id", "group", "query", "intent"):
        if not str(case.get(field, "")).strip():
            errors.append(f"{field} is empty")
    if not _is_valid_matchers(case.get("relevant")):
        errors.append("relevant must contain non-empty keyword matchers")
    if not _is_valid_text_list(case.get("guardrails")):
        errors.append("guardrails must contain non-empty text")
    sensitive_scenarios = case.get("sensitive_scenarios")
    if sensitive_scenarios is not None and not _is_valid_sensitive_scenarios(
        sensitive_scenarios
    ):
        errors.append("sensitive_scenarios contains unknown or empty value")
    return errors


def _is_valid_matchers(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(_is_valid_text_list(matcher) for matcher in value)


def _is_valid_text_list(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(isinstance(item, str) and item.strip() for item in value)


def _check_required_groups(groups: set[str]) -> list[GoldenCaseCheck]:
    return [
        GoldenCaseCheck(
            f"group.{group}",
            group in groups,
            "" if group in groups else "required group missing",
        )
        for group in REQUIRED_GROUPS
    ]


def _is_valid_sensitive_scenarios(value: object) -> bool:
    return _is_valid_text_list(value) and all(
        str(item) in REQUIRED_SENSITIVE_SCENARIOS for item in value
    )


def _check_sensitive_scenarios(cases: list[object]) -> list[GoldenCaseCheck]:
    counts = {scenario: 0 for scenario in REQUIRED_SENSITIVE_SCENARIOS}
    for case in cases:
        if not isinstance(case, dict):
            continue
        sensitive_scenarios = case.get("sensitive_scenarios")
        if not isinstance(sensitive_scenarios, list):
            continue
        for scenario in set(str(item) for item in sensitive_scenarios):
            if scenario in counts:
                counts[scenario] += 1
    return [
        GoldenCaseCheck(
            f"sensitive.{scenario}",
            count >= MIN_SENSITIVE_CASES_PER_SCENARIO,
            (
                ""
                if count >= MIN_SENSITIVE_CASES_PER_SCENARIO
                else f"expected >= {MIN_SENSITIVE_CASES_PER_SCENARIO}, got {count}"
            ),
        )
        for scenario, count in counts.items()
    ]


def build_sensitive_policy_checks(case: dict[str, object]) -> list[GoldenCaseCheck]:
    """按敏感场景生成 guardrail 策略契约检查。"""
    case_id = str(case.get("id", "case"))
    sensitive_scenarios = case.get("sensitive_scenarios")
    if not isinstance(sensitive_scenarios, list):
        return []
    guardrail_text = "\n".join(str(item) for item in case.get("guardrails", []))
    return [
        _build_sensitive_policy_check(case_id, str(scenario), guardrail_text)
        for scenario in sensitive_scenarios
        if str(scenario) in SENSITIVE_SCENARIO_POLICY_KEYWORDS
    ]


def _build_sensitive_policy_check(
    case_id: str,
    scenario: str,
    guardrail_text: str,
) -> GoldenCaseCheck:
    missing_groups = [
        " / ".join(keyword_group)
        for keyword_group in SENSITIVE_SCENARIO_POLICY_KEYWORDS[scenario]
        if not any(keyword in guardrail_text for keyword in keyword_group)
    ]
    return GoldenCaseCheck(
        f"{case_id}.sensitive_policy.{scenario}",
        not missing_groups,
        "" if not missing_groups else f"missing policy keywords: {missing_groups}",
    )


def build_forbidden_reply_patterns(case: dict[str, object]) -> list[str]:
    """按敏感场景派生禁止回复模式。"""
    sensitive_scenarios = case.get("sensitive_scenarios")
    if not isinstance(sensitive_scenarios, list):
        return []
    patterns: list[str] = []
    seen_patterns: set[str] = set()
    for scenario in sensitive_scenarios:
        scenario_patterns = SENSITIVE_SCENARIO_FORBIDDEN_REPLY_PATTERNS.get(
            str(scenario),
            (),
        )
        for pattern in scenario_patterns:
            if pattern in seen_patterns:
                continue
            patterns.append(pattern)
            seen_patterns.add(pattern)
    return patterns


def _check_sensitive_output_policies() -> list[GoldenCaseCheck]:
    return [
        GoldenCaseCheck(
            f"sensitive_output_policy.{scenario}",
            bool(SENSITIVE_SCENARIO_FORBIDDEN_REPLY_PATTERNS.get(scenario)),
            "forbidden reply patterns required",
        )
        for scenario in REQUIRED_SENSITIVE_SCENARIOS
    ]


def build_json_report(checks: list[GoldenCaseCheck]) -> dict[str, object]:
    failed_checks = [check for check in checks if not check.passed]
    return {
        "status": "passed" if not failed_checks else "failed",
        "metadata": {
            "generated_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "fixture": str(FIXTURE_PATH),
        },
        "total": len(checks),
        "failed": len(failed_checks),
        "checks": [check.to_dict() for check in checks],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check customer RAG golden cases")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    checks = validate_fixture(load_fixture())
    report = build_json_report(checks)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "customer_rag_golden_cases "
            f"status={report['status']} total={report['total']} failed={report['failed']}"
        )
    else:
        print(f"customer_rag_golden_cases status={report['status']}")
        for check in checks:
            mark = "OK" if check.passed else "FAIL"
            print(f"[{mark}] {check.name} {check.detail}".rstrip())
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
