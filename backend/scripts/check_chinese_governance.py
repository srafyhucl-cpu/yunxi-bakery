"""检查 Harness P0 中文治理控制面。"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from check_project_development_register import parse_register
except ModuleNotFoundError:
    from scripts.check_project_development_register import parse_register

ROOT_DIR = Path(__file__).resolve().parents[2]
STATUS_LABELS = {
    "active": "进行中（active）",
    "blocked": "已阻塞（blocked）",
    "completed": "已完成（completed）",
    "pending": "待处理（pending）",
    "deferred": "已暂缓（deferred）",
    "historical": "历史（historical）",
}
MACHINE_STATUS_RE = re.compile(
    r"(?<![\w（(])(active|blocked|completed|pending|deferred|historical)(?![\w）)])",
    re.IGNORECASE,
)
AUTHORITATIVE_FILES = ("AGENTS.md", "PROJECT-STATE.md", "LOGBOOK.md", "ERRORS.md")
GOVERNANCE_FILES = (
    "AGENTS.md",
    "PROJECT-STATE.md",
    "LOGBOOK.md",
    "ERRORS.md",
    "docs/harness-engineering/README.md",
    "docs/harness-engineering/core/traceability-model.md",
    "docs/harness-engineering/core/verification-matrix.md",
    "docs/harness-engineering/core/agent-handoff-template.md",
    "docs/AGENTS/multi-agent-coordination.md",
)
HIGH_RISK_FILES = (
    "backend/scripts/preflight_production.py",
    "backend/scripts/check_privacy_outbound_contract.py",
    "backend/scripts/check_security_outbound_contract.py",
    "backend/scripts/smoke_test.py",
    "miniapp/docs/release/manual-acceptance-checklist.md",
)
HIGH_RISK_REQUIRED_TEXT = {
    "backend/scripts/preflight_production.py": (
        "生产同步前只读预检报告",
        "阻断",
        "人工接手",
    ),
    "backend/scripts/check_privacy_outbound_contract.py": (
        "模型外发脱敏",
        "trace",
        "生产关闭态",
    ),
    "backend/scripts/check_security_outbound_contract.py": (
        "远程下载",
        "员工授权出站合同",
        "生产",
    ),
    "backend/scripts/smoke_test.py": (
        "上线前只读冒烟检查",
        "请求失败",
        "生产",
    ),
    "miniapp/docs/release/manual-acceptance-checklist.md": (
        "只用于开发测试和上线准备",
        "真实用户",
        "正式上线",
        "支付",
    ),
}
REQUIRED_REFERENCES = {
    "docs/harness-engineering/README.md": (
        "PROJECT-STATE.md",
        "LOGBOOK.md",
        "ERRORS.md",
        "Harness",
    ),
    "docs/harness-engineering/core/traceability-model.md": (
        "run_id",
        "replayable",
        "中文",
    ),
    "docs/harness-engineering/core/agent-handoff-template.md": (
        "trace_id",
        "run_id",
        "已完成",
        "未验证",
    ),
    "docs/harness-engineering/core/verification-matrix.md": (
        "Harness 中文治理",
        "P0",
    ),
}


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    details: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "details": list(self.details)}


def has_chinese(text: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in text)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def check_authoritative_files(root_dir: Path = ROOT_DIR) -> Check:
    missing = [path for path in AUTHORITATIVE_FILES if not (root_dir / path).is_file()]
    return Check(
        "中文权威入口",
        not missing,
        tuple(f"缺少权威入口: {path}" for path in missing),
    )


def check_authoritative_references(root_dir: Path = ROOT_DIR) -> Check:
    issues: list[str] = []
    for relative, required in REQUIRED_REFERENCES.items():
        path = root_dir / relative
        if not path.is_file():
            issues.append(f"文件不存在: {relative}")
            continue
        text = _read(path)
        for token in required:
            if token not in text:
                issues.append(f"{relative}: 缺少治理标识 {token}")
    return Check("权威入口与治理引用", not issues, tuple(issues))


def check_project_state(root_dir: Path = ROOT_DIR) -> Check:
    result = parse_register(root_dir / "PROJECT-STATE.md")
    issues = tuple(issue for issue in result.issues if "中文" in issue)
    return Check("项目状态中文展示", not issues, issues)


def _task_metadata(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in _read(path).splitlines():
        match = re.match(r"^\s*(?:>\s*)?([a-z_]+):\s*(.*?)\s*$", line)
        if match:
            fields[match.group(1)] = match.group(2).strip()
        elif fields:
            break
    return fields


def check_task_status_labels(root_dir: Path = ROOT_DIR) -> Check:
    tasks_dir = root_dir / "docs" / "tasks"
    if not tasks_dir.is_dir():
        return Check("任务中文状态标签", False, ("缺少 docs/tasks 目录",))
    issues: list[str] = []
    checked = 0
    for path in sorted(tasks_dir.glob("*.md")):
        metadata = _task_metadata(path)
        if "status" not in metadata:
            continue
        checked += 1
        expected = STATUS_LABELS.get(metadata.get("status", ""))
        actual = metadata.get("status_label", "")
        if expected and actual != expected:
            issues.append(
                f"{path.relative_to(root_dir)}: status_label 应为 {expected}，实际为 {actual or '<empty>'}"
            )
    if not checked:
        issues.append("未发现带 status 元数据的任务指令")
    return Check("任务中文状态标签", not issues, tuple(issues))


def _human_lines_without_fences(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    in_fence = False
    for line_no, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append((line_no, line))
    return lines


def check_project_state_no_bare_status(root_dir: Path = ROOT_DIR) -> Check:
    path = root_dir / "PROJECT-STATE.md"
    if not path.is_file():
        return Check("禁止裸机器状态码", False, ("PROJECT-STATE.md 不存在",))
    issues: list[str] = []
    for line_no, line in _human_lines_without_fences(_read(path)):
        if re.match(
            r"^\s*\|.*\|\s*(active|blocked|completed|pending|deferred|historical)\s*\|",
            line,
            re.IGNORECASE,
        ):
            continue
        if re.match(
            r"^\s*(?:>\s*)?(?:status|status_label)\s*:",
            line,
            re.IGNORECASE,
        ):
            continue
        match = MACHINE_STATUS_RE.search(line)
        if match and "（" not in line and "(" not in line:
            issues.append(
                f"PROJECT-STATE.md:{line_no}: 状态码 {match.group(1)} 缺少中文标签"
            )
    return Check("禁止裸机器状态码", not issues, tuple(issues))


def check_governance_file_coverage(root_dir: Path = ROOT_DIR) -> Check:
    issues: list[str] = []
    checked = 0
    for relative in GOVERNANCE_FILES:
        path = root_dir / relative
        if not path.is_file():
            issues.append(f"文件不存在: {relative}")
            continue
        checked += 1
        if not has_chinese(_read(path)):
            issues.append(f"缺少中文人类可读内容: {relative}")
    if checked == 0:
        issues.append("没有可统计的治理文件")
    return Check("治理文档中文覆盖", not issues, tuple(issues))


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _literal_cli_text(path: Path) -> tuple[str, ...]:
    """提取 argparse 中真正展示给 CLI 使用者的字面量文本。"""
    tree = ast.parse(_read(path), filename=str(path))
    values: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node)
        if call_name not in {"ArgumentParser", "add_argument"}:
            continue
        for keyword in node.keywords:
            if keyword.arg not in {"description", "epilog", "help"}:
                continue
            if isinstance(keyword.value, ast.Constant) and isinstance(
                keyword.value.value, str
            ):
                values.append(keyword.value.value)
    return tuple(values)


def _high_risk_readable_text(path: Path) -> tuple[str, ...]:
    if path.suffix != ".py":
        return (_read(path),)
    return _literal_cli_text(path)


def check_high_risk_path_readability(root_dir: Path = ROOT_DIR) -> Check:
    issues: list[str] = []
    for relative in HIGH_RISK_FILES:
        path = root_dir / relative
        if not path.is_file():
            issues.append(f"高风险文件不存在: {relative}")
            continue
        try:
            text = "\n".join(_high_risk_readable_text(path))
        except (OSError, SyntaxError) as exc:
            issues.append(f"{relative}: 无法解析高风险用户可见文本: {exc}")
            continue
        required = HIGH_RISK_REQUIRED_TEXT.get(relative, ())
        missing = [token for token in required if token not in text]
        if missing:
            issues.append(f"{relative}: 高风险语义断言缺失: {', '.join(missing)}")
    return Check("高风险路径中文可读性", not issues, tuple(issues))


def build_report(root_dir: Path = ROOT_DIR) -> dict[str, object]:
    checks = (
        check_authoritative_files,
        check_authoritative_references,
        check_project_state,
        check_task_status_labels,
        check_project_state_no_bare_status,
        check_governance_file_coverage,
        check_high_risk_path_readability,
    )
    results = [check(root_dir) for check in checks]
    existing = [
        root_dir / relative
        for relative in GOVERNANCE_FILES
        if (root_dir / relative).is_file()
    ]
    chinese = [path for path in existing if has_chinese(_read(path))]
    issues = [
        f"{result.name}: {detail}"
        for result in results
        if not result.passed
        for detail in result.details
    ]
    return {
        "status": "passed" if not issues else "failed",
        "checks": [result.to_dict() for result in results],
        "coverage": {
            "governance_files": len(existing),
            "files_with_chinese": len(chinese),
            "ratio": round(len(chinese) / len(existing), 4) if existing else 0.0,
        },
        "issues": issues,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查 Harness P0 中文治理")
    parser.add_argument("--root", type=Path, default=ROOT_DIR)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args(argv)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(f"拒绝覆盖已有中文治理报告: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = build_report(args.root.resolve())
        if args.json_out:
            _write_json(args.json_out, report)
    except (OSError, ValueError) as exc:
        print(f"[中文治理] FAIL {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        coverage = report["coverage"]
        print(
            "chinese_governance "
            f"status={report['status']} files={coverage['governance_files']} "
            + f"chinese={coverage['files_with_chinese']} coverage={coverage['ratio']} "
            + f"failed={len(report['issues'])}"
        )
    elif report["issues"]:
        print("[中文治理] FAIL")
        for issue in report["issues"]:
            print(f"  - {issue}")
    else:
        print(f"[中文治理] PASS coverage={report['coverage']['ratio']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
