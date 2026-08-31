"""只读扫描文档断链、入口漂移、孤立任务和低风险中文覆盖。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
TASK_METADATA_RE = re.compile(
    r"^>\s*(task_id|status|as_of_commit):\s*(.*?)\s*$", re.MULTILINE
)
TASK_TABLE_RE = re.compile(r"^\|\s*([A-Z0-9][A-Z0-9_-]*)\s*\|", re.MULTILINE)
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


@dataclass(frozen=True)
class Finding:
    severity: str
    rule: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "rule": self.rule,
            "path": self.path,
            "message": self.message,
        }


def has_chinese(text: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in text)


def markdown_files(root_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for relative in (
        "docs",
        "AGENTS.md",
        "PROJECT-STATE.md",
        "LOGBOOK.md",
        "ERRORS.md",
        "miniapp/AGENTS.md",
    ):
        candidate = root_dir / relative
        if candidate.is_file() and candidate.suffix.lower() == ".md":
            paths.append(candidate)
        elif candidate.is_dir():
            paths.extend(
                path
                for path in candidate.rglob("*.md")
                if ".git" not in path.parts and "reports" not in path.parts
            )
    return sorted(set(paths))


def _rel(path: Path, root_dir: Path) -> str:
    try:
        return path.resolve().relative_to(root_dir.resolve()).as_posix()
    except ValueError:
        return str(path)


def scan_links(path: Path, root_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8-sig")
    in_fence = False
    for line_no, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for raw_target in LINK_RE.findall(line):
            target = unquote(
                raw_target.strip().split("#", 1)[0].split("?", 1)[0].strip("<>").strip()
            )
            if not target or target.startswith(
                ("http://", "https://", "mailto:", "tel:")
            ):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                severity = "warning" if "archive" in path.parts else "error"
                findings.append(
                    Finding(
                        severity,
                        "broken_link",
                        _rel(path, root_dir),
                        f"第 {line_no} 行链接目标不存在: {target}",
                    )
                )
    return findings


def _git_resolves(root_dir: Path, commit: str) -> bool:
    if not SHA_RE.fullmatch(commit):
        return False
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=root_dir,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def scan_tasks(root_dir: Path, findings: list[Finding]) -> None:
    state_text = (root_dir / "PROJECT-STATE.md").read_text(encoding="utf-8-sig")
    state_ids = set(TASK_TABLE_RE.findall(state_text))
    seen: dict[str, str] = {}
    for path in sorted((root_dir / "docs" / "tasks").glob("*.md")):
        metadata = dict(TASK_METADATA_RE.findall(path.read_text(encoding="utf-8-sig")))
        task_id = metadata.get("task_id")
        if not task_id:
            continue
        relative = _rel(path, root_dir)
        if task_id in seen:
            findings.append(
                Finding(
                    "warning",
                    "duplicate_task_id",
                    relative,
                    f"task_id {task_id} 与 {seen[task_id]} 重复",
                )
            )
        seen[task_id] = relative
        if task_id not in state_ids:
            findings.append(
                Finding(
                    "warning",
                    "orphan_task",
                    relative,
                    f"task_id {task_id} 未出现在 PROJECT-STATE.md",
                )
            )
        commit = metadata.get("as_of_commit", "")
        if commit and not _git_resolves(root_dir, commit):
            findings.append(
                Finding(
                    "warning",
                    "stale_snapshot",
                    relative,
                    f"as_of_commit 无法在当前仓解析: {commit}",
                )
            )


def scan_canonical_entries(root_dir: Path, findings: list[Finding]) -> None:
    mirror = root_dir / "docs" / "harness-engineering" / "core" / "mistake-ledger.md"
    canonical = root_dir / "ERRORS.md"
    if mirror.exists() and canonical.exists():
        text = mirror.read_text(encoding="utf-8-sig")
        if "ERRORS.md" not in text or "不再承载正式错误条目" not in text:
            findings.append(
                Finding(
                    "error",
                    "canonical_mirror",
                    _rel(mirror, root_dir),
                    "历史错误账本镜像未明确指向根目录 ERRORS.md",
                )
            )


def scan_chinese_coverage(root_dir: Path, findings: list[Finding]) -> None:
    for path in sorted((root_dir / "docs" / "tasks").glob("*.md")):
        if not has_chinese(path.read_text(encoding="utf-8-sig")):
            findings.append(
                Finding(
                    "warning",
                    "low_risk_chinese",
                    _rel(path, root_dir),
                    "任务文档缺少中文人类可读内容",
                )
            )


def scan_unregistered_manifests(root_dir: Path, findings: list[Finding]) -> None:
    evidence = (
        root_dir / "docs" / "harness-engineering" / "core" / "evidence-index.md"
    ).read_text(encoding="utf-8-sig")
    report_dir = root_dir / "backend" / "reports" / "harness"
    for path in sorted(report_dir.glob("*.run.json")):
        relative = _rel(path, root_dir)
        if relative not in evidence and path.name.startswith("p0-gate-") is False:
            findings.append(
                Finding(
                    "warning",
                    "unregistered_report",
                    relative,
                    "运行 manifest 未在 evidence-index.md 登记",
                )
            )


def build_report(root_dir: Path = ROOT_DIR) -> dict[str, Any]:
    findings: list[Finding] = []
    files = markdown_files(root_dir)
    for path in files:
        findings.extend(scan_links(path, root_dir))
    scan_tasks(root_dir, findings)
    scan_canonical_entries(root_dir, findings)
    scan_chinese_coverage(root_dir, findings)
    scan_unregistered_manifests(root_dir, findings)
    errors = sum(1 for finding in findings if finding.severity == "error")
    warnings = sum(1 for finding in findings if finding.severity == "warning")
    return {
        "schema_version": "1.0",
        "scan_type": "documentation_garden",
        "generated_at": __import__("datetime")
        .datetime.now(__import__("datetime").timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "status": "passed" if errors == 0 else "failed",
        "files_scanned": len(files),
        "summary": {"errors": errors, "warnings": warnings},
        "findings": [finding.to_dict() for finding in findings],
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"拒绝覆盖已有文档园艺报告: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="扫描文档园艺与低风险中文维护问题")
    parser.add_argument("--root", type=Path, default=ROOT_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--fail-on", choices=("error", "warning", "never"), default="error"
    )
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(sys.argv[1:] if argv is None else argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build_report(args.root.resolve())
        if args.output:
            write_report(args.output, report)
    except (OSError, ValueError) as exc:
        print(f"[文档园艺] FAIL {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        summary = report["summary"]
        print(
            f"doc_garden status={report['status']} files={report['files_scanned']} errors={summary['errors']} warnings={summary['warnings']}"
        )
    else:
        print(
            f"[文档园艺] {'PASS' if report['status'] == 'passed' else 'FAIL'} files={report['files_scanned']}"
        )
    summary = report["summary"]
    if args.fail_on == "never":
        return 0
    if args.fail_on == "warning" and summary["warnings"]:
        return 1
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
