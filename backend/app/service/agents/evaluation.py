"""Agent Eval 通用报告模型。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CASE_GROUP = "ungrouped"


@dataclass(frozen=True)
class AgentEvalAssertion:
    """单条 eval 断言结果。"""

    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AgentEvalCase:
    """单个 Agent eval case。"""

    case_id: str
    agent: str
    query: str
    group: str = ""
    intent: str = ""
    tools: tuple[str, ...] = ()
    assertions: tuple[AgentEvalAssertion, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(assertion.passed for assertion in self.assertions)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.case_id,
            "agent": self.agent,
            "group": self.group,
            "query": self.query,
            "intent": self.intent,
            "tools": list(self.tools),
            "passed": self.passed,
            "assertions": [assertion.to_dict() for assertion in self.assertions],
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AgentEvalResult:
    """单个 Agent eval 汇总。"""

    agent: str
    cases: tuple[AgentEvalCase, ...]
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def failed(self) -> int:
        return sum(1 for case in self.cases if not case.passed)

    @property
    def status(self) -> str:
        return "passed" if self.failed == 0 else "failed"

    @property
    def pass_rate(self) -> float:
        if not self.total:
            return 0.0
        return round((self.total - self.failed) / self.total, 4)

    def to_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "status": self.status,
            "total": self.total,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "metadata": self.metadata,
            "case_groups": summarize_eval_cases_by_group(self.cases),
            "sensitive_scenarios": summarize_eval_cases_by_sensitive_scenario(
                self.cases
            ),
            "cases": [case.to_dict() for case in self.cases],
            "failed_ids": [case.case_id for case in self.cases if not case.passed],
        }


def combine_agent_eval_results(
    results: tuple[AgentEvalResult, ...],
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """聚合多个 Agent eval 结果。"""
    total = sum(result.total for result in results)
    failed = sum(result.failed for result in results)
    return {
        "status": "passed" if failed == 0 else "failed",
        "total": total,
        "failed": failed,
        "pass_rate": round((total - failed) / total, 4) if total else 0.0,
        "metadata": metadata or {},
        "agent_totals": summarize_agent_eval_results(results),
        "case_groups": summarize_eval_cases_by_group(
            tuple(case for result in results for case in result.cases)
        ),
        "sensitive_scenarios": summarize_eval_cases_by_sensitive_scenario(
            tuple(case for result in results for case in result.cases)
        ),
        "agents": [result.to_dict() for result in results],
    }


def summarize_agent_eval_results(
    results: tuple[AgentEvalResult, ...],
) -> list[dict[str, object]]:
    """按 agent 汇总 eval 结果，便于报告展示。"""
    return [
        {
            "agent": result.agent,
            "status": result.status,
            "total": result.total,
            "failed": result.failed,
            "pass_rate": result.pass_rate,
        }
        for result in results
    ]


def summarize_eval_cases_by_group(
    cases: tuple[AgentEvalCase, ...],
) -> list[dict[str, object]]:
    """按 case group 汇总 eval 结果，便于作品集展示覆盖面。"""
    grouped_cases: dict[str, list[AgentEvalCase]] = {}
    for case in cases:
        group_name = case.group or DEFAULT_CASE_GROUP
        grouped_cases.setdefault(group_name, []).append(case)
    return [
        _build_case_group_summary(group_name, tuple(group_cases))
        for group_name, group_cases in sorted(grouped_cases.items())
    ]


def _build_case_group_summary(
    group_name: str,
    cases: tuple[AgentEvalCase, ...],
) -> dict[str, object]:
    failed = sum(1 for case in cases if not case.passed)
    total = len(cases)
    return {
        "group": group_name,
        "total": total,
        "failed": failed,
        "passed": total - failed,
        "pass_rate": round((total - failed) / total, 4) if total else 0.0,
    }


def summarize_eval_cases_by_sensitive_scenario(
    cases: tuple[AgentEvalCase, ...],
) -> list[dict[str, object]]:
    """按事实敏感场景汇总 eval 结果。"""
    grouped_cases: dict[str, list[AgentEvalCase]] = {}
    for case in cases:
        scenario_values = case.metadata.get("sensitive_scenarios")
        if not isinstance(scenario_values, list):
            continue
        for scenario in scenario_values:
            scenario_name = str(scenario).strip()
            if scenario_name:
                grouped_cases.setdefault(scenario_name, []).append(case)
    return [
        _build_sensitive_scenario_summary(scenario, tuple(scenario_cases))
        for scenario, scenario_cases in sorted(grouped_cases.items())
    ]


def _build_sensitive_scenario_summary(
    scenario: str,
    cases: tuple[AgentEvalCase, ...],
) -> dict[str, object]:
    failed = sum(1 for case in cases if not case.passed)
    total = len(cases)
    return {
        "scenario": scenario,
        "total": total,
        "failed": failed,
        "passed": total - failed,
        "pass_rate": round((total - failed) / total, 4) if total else 0.0,
    }


def filter_agent_eval_result(
    result: AgentEvalResult,
    case_ids: tuple[str, ...] = (),
) -> AgentEvalResult:
    """按稳定 case_id 过滤 eval 结果。"""
    if not case_ids:
        return result
    selected_ids = set(case_ids)
    return AgentEvalResult(
        agent=result.agent,
        cases=tuple(case for case in result.cases if case.case_id in selected_ids),
        metadata={**result.metadata, "case_filter": list(case_ids)},
    )


def apply_fail_fast(result: AgentEvalResult) -> AgentEvalResult:
    """保留到首个失败 case，便于快速定位。"""
    kept_cases: list[AgentEvalCase] = []
    for case in result.cases:
        kept_cases.append(case)
        if not case.passed:
            break
    return AgentEvalResult(
        agent=result.agent,
        cases=tuple(kept_cases),
        metadata={**result.metadata, "fail_fast": True},
    )


def write_json_report(payload: dict[str, object], output_path: Path) -> None:
    """写入 UTF-8 JSON 报告，父目录不存在时自动创建。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
