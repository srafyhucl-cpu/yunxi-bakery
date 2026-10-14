"""GitHub 参考实施计划静态验收。"""

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
    / "github-reference-benchmark-and-implementation-plan.md"
)

REQUIRED_STATUS_PHRASES = (
    "阶段 0 已冻结",
    "阶段 1 首版能力目录已执行",
    "阶段 2 上下文治理小切片已执行",
    "阶段 3 知识库治理",
    "阶段 4 员工助手能力合约清单首版已执行",
    "阶段 5 Platform 侧和 MiniApp 仓页面 API 覆盖合约首版已执行",
    "阶段 6 客户机器人可观测合约、MiniApp 仓可观测合约和 miniprogram-ci 发布准备合约首版已执行",
)
REQUIRED_BOUNDARIES = (
    "不建议迁移客户热路径和员工助手主链路",
    "员工助手不能 Agent 化成自由推理",
    "MiniApp 不能沉淀业务真相",
    "长期记忆不能直接等于聊天摘要",
    "不改客户机器人热路径",
    "不改员工助手 planner、工具调用或确定性回复",
    "不执行真实上传、不生成体验版、不替代真机验收",
)
REQUIRED_ARTIFACTS = (
    "bot-capability-matrix.md",
    "customer-session-summary-design.md",
    "customer-memory-governance-plan.md",
    "customer-observability-contract.md",
    "miniapp-page-api-coverage-contract.md",
    "knowledge-governance-migration-plan.md",
    "docs/release/miniprogram-ci-readiness.md",
    "scripts/check-miniprogram-ci-readiness.mjs",
    "scripts/check_project.py --skip-tests",
    "scripts/preflight_production.py --json",
)
REQUIRED_LANGGRAPH_LIMITS = (
    "LangGraph 离线流程试点（可选",
    "不进入客户实时回复",
    "不影响员工助手事实回复",
    "节点和最大循环次数写死",
    "保留现有 offline agent 作为回滚路径",
)
FORBIDDEN_DIRECTIVES = (
    "全量 LangChain 改造已批准",
    "迁移客户机器人热路径到 LangChain",
    "员工助手最终回复交给 LLM",
    "MiniApp 本地计算真实会员权益",
    "直接上传体验版且无需密钥边界",
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
        *_check_required_items("boundary", REQUIRED_BOUNDARIES, content),
        *_check_required_items("artifact", REQUIRED_ARTIFACTS, content),
        *_check_required_items("langgraph_limit", REQUIRED_LANGGRAPH_LIMITS, content),
        *_check_forbidden_directives(content),
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


def _check_forbidden_directives(content: str) -> list[PlanCheck]:
    return [
        PlanCheck(
            f"forbidden.{item}",
            item not in content,
            "" if item not in content else "forbidden implementation directive found",
        )
        for item in FORBIDDEN_DIRECTIVES
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
        description="Check GitHub reference implementation plan"
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
            "github_reference_implementation_plan "
            f"status={report['status']} total={report['total']} failed={report['failed']}"
        )
    else:
        print(f"github_reference_implementation_plan status={report['status']}")
        for check in checks:
            mark = "OK" if check.passed else "FAIL"
            print(f"[{mark}] {check.name} {check.detail}".rstrip())
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
