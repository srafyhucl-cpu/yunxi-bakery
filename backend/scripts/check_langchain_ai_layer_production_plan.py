"""LangChain AI 应用层生产增强计划静态验收。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PLAN_PATH = (
    ROOT_DIR
    / "docs"
    / "architecture"
    / "langchain-ai-layer-production-enhancement-plan.md"
)

REQUIRED_STATUS_PHRASES = (
    "状态：持续执行中",
    "P0-P14c 已完成",
    "下一步建议进入 P17b",
)
REQUIRED_ARTIFACTS = (
    "scripts/check_langchain_ai_layer_release_gate.py",
    "scripts/check_real_conversation_replay.py",
    "scripts/export_real_conversation_replay_fixture.py",
    "scripts/check_real_conversation_replay_coverage.py",
    "scripts/build_real_conversation_replay_intake_packet.py",
    "scripts/prepare_real_conversation_replay_pool_entry.py",
    "scripts/check_real_conversation_replay_intake_readiness.py",
    "scripts/check_langchain_production_observability_release.py",
    "scripts/audit_real_conversation_replay_candidate.py",
    "scripts/check_langchain_production_runtime_version.py",
    "scripts/report_langchain_production_sync_handoff.py",
    "scripts/report_langchain_production_callback_failures.py",
    "scripts/check_langsmith_runtime_config.py",
    "scripts/check_langsmith_production_rollout.py",
    "scripts/build_langsmith_production_enablement_packet.py",
    "scripts/check_langchain_ai_layer_capacity.py",
    "scripts/report_rag_shadow_observability.py",
    "scripts/report_rag_shadow_log_observability.py",
    "scripts/build_rag_shadow_log_intake_packet.py",
    "scripts/build_langchain_release_evidence_packet.py",
    "scripts/build_langchain_portfolio_evidence_packet.py",
    "scripts/build_langchain_external_evidence_handoff_packet.py",
    "tests/fixtures/customer_real_replay_coverage_sample.json",
    "docs/harness-engineering/core/evidence-index.md",
)
REQUIRED_BOUNDARIES = (
    "合成覆盖样例不等同真实客服样本池",
    "不访问生产、不读取业务数据库、不调用外部 LLM、不改变客户或员工热路径",
    "真实样本应替换或补充当前合成覆盖样例",
    "LangSmith 仍保持可选配置能力",
    "生产接口真实版本必须与本地目标版本一致",
    "不得通过放宽 release gate、callback 语义断言或版本检查来制造通过",
    "公网 /health 和 /ready 运行时版本必须单独验收",
)
REQUIRED_EXTERNAL_HANDOFF_CONTRACTS = (
    "action_groups",
    "action_group_details",
    "pre_submission_checklist_summary",
    "precheck_items=10",
    "--markdown-out",
    "LangChain 外部证据交接包",
)
FORBIDDEN_STALE_PHRASES = (
    "状态：计划冻结，待执行",
    "下一步建议直接进入阶段 P0",
    "下一步建议进入 P12",
    "下一步建议进入 P14 生产版本同步与 callback 失败定位",
    "下一步建议进入 P14b 生产服务重启与 callback 失败定位",
    "下一步建议进入 P14c 生产部署重启与 callback 复验",
    "P0-P14b 已完成",
    "P11d 把真实 replay 数量扩到每类事实敏感场景至少 5 条",
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
        *_check_required_items("status", REQUIRED_STATUS_PHRASES, content),
        *_check_required_items("artifact", REQUIRED_ARTIFACTS, content),
        *_check_required_items("boundary", REQUIRED_BOUNDARIES, content),
        *_check_required_items(
            "external_handoff_contract",
            REQUIRED_EXTERNAL_HANDOFF_CONTRACTS,
            content,
        ),
        *_check_forbidden_stale_phrases(content),
        _check_no_placeholders(content),
    ]


def _check_required_items(
    prefix: str,
    items: tuple[str, ...],
    content: str,
) -> list[PlanCheck]:
    return [
        PlanCheck(
            f"{prefix}.{item}",
            item in content,
            "" if item in content else f"required {prefix} missing",
        )
        for item in items
    ]


def _check_forbidden_stale_phrases(content: str) -> list[PlanCheck]:
    return [
        PlanCheck(
            f"stale.{item}",
            item not in content,
            "" if item not in content else "stale plan phrase found",
        )
        for item in FORBIDDEN_STALE_PHRASES
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
        description="Check LangChain AI layer production enhancement plan"
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
            "langchain_ai_layer_production_plan "
            f"status={report['status']} total={report['total']} failed={report['failed']}"
        )
    else:
        print(f"langchain_ai_layer_production_plan status={report['status']}")
        for check in checks:
            mark = "OK" if check.passed else "FAIL"
            print(f"[{mark}] {check.name} {check.detail}".rstrip())
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
