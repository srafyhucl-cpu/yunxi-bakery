"""生成 Harness 交接快照。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
LOGBOOK_FILE = ROOT_DIR / "LOGBOOK.md"
HARNESS_DOC = ROOT_DIR / "docs" / "harness-engineering" / "README.md"
SPEC_DOC = (
    ROOT_DIR
    / "docs"
    / "harness-engineering"
    / "specs"
    / "2026-06-11-vibe-coding-harness-engineering-design.md"
)
OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
UTF8_BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class GitStatus:
    modified_files: tuple[str, ...]
    untracked_files: tuple[str, ...]
    other_files: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.modified_files or self.untracked_files or self.other_files)


@dataclass(frozen=True)
class HarnessSnapshot:
    trace_id: str
    goal: str
    generated_at: str
    current_status: str
    latest_logbook_entry: str
    git_status: GitStatus
    reference_entries: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "trace_id": self.trace_id,
            "goal": self.goal,
            "generated_at": self.generated_at,
            "current_status": self.current_status,
            "latest_logbook_entry": self.latest_logbook_entry,
            "git_status": {
                "modified_files": list(self.git_status.modified_files),
                "untracked_files": list(self.git_status.untracked_files),
                "other_files": list(self.git_status.other_files),
                "has_changes": self.git_status.has_changes,
            },
            "reference_entries": list(self.reference_entries),
        }


def run_git_status(root_dir: Path = ROOT_DIR) -> GitStatus:
    completed = subprocess.run(
        ["git", "-c", "core.quotepath=false", "status", "--short"],
        cwd=root_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return GitStatus((), (), (f"git status failed: {completed.stderr.strip()}",))
    return parse_git_status(completed.stdout)


def parse_git_status(status_text: str) -> GitStatus:
    modified_files: list[str] = []
    untracked_files: list[str] = []
    other_files: list[str] = []
    for raw_line in status_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        status_code = line[:2]
        file_path = line[3:].strip() if len(line) > 3 else line.strip()
        if status_code == "??":
            untracked_files.append(file_path)
        elif "M" in status_code or "A" in status_code or "D" in status_code:
            modified_files.append(file_path)
        else:
            other_files.append(line)
    return GitStatus(
        tuple(modified_files),
        tuple(untracked_files),
        tuple(other_files),
    )


def read_latest_logbook_entry(logbook_file: Path = LOGBOOK_FILE) -> str:
    if not logbook_file.exists():
        return "LOGBOOK.md not found"
    for line in logbook_file.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("## "):
            return line.removeprefix("## ").strip()
    return "no logbook entry found"


def build_reference_entries(root_dir: Path = ROOT_DIR) -> tuple[str, ...]:
    candidates = (
        root_dir / "AGENTS.md",
        root_dir / "LOGBOOK.md",
        root_dir / "docs" / "harness-engineering" / "README.md",
        root_dir / "docs" / "harness-engineering" / "core" / "verification-matrix.md",
        root_dir / "docs" / "harness-engineering" / "core" / "mistake-ledger.md",
        root_dir
        / "docs"
        / "harness-engineering"
        / "core"
        / "agent-handoff-template.md",
    )
    return tuple(
        str(path.relative_to(root_dir)).replace("\\", "/")
        for path in candidates
        if path.exists()
    )


def build_snapshot(
    *,
    trace_id: str,
    goal: str,
    current_status: str,
    root_dir: Path = ROOT_DIR,
) -> HarnessSnapshot:
    generated_at = datetime.now(timezone.utc).isoformat()
    return HarnessSnapshot(
        trace_id=trace_id,
        goal=goal,
        generated_at=generated_at,
        current_status=current_status,
        latest_logbook_entry=read_latest_logbook_entry(root_dir / "LOGBOOK.md"),
        git_status=run_git_status(root_dir),
        reference_entries=build_reference_entries(root_dir),
    )


def format_markdown(snapshot: HarnessSnapshot) -> str:
    lines = [
        "# Agent Handoff",
        "",
        f"- trace_id: {snapshot.trace_id}",
        f"- generated_at: {snapshot.generated_at}",
        "- owner: AI (Codex)",
        f"- current_goal: {snapshot.goal}",
        f"- current_status: {snapshot.current_status}",
        f"- latest_logbook_entry: {snapshot.latest_logbook_entry}",
        "",
        "## 当前工作区",
        "",
        "- modified_files:",
    ]
    lines.extend(format_items(snapshot.git_status.modified_files))
    lines.append("- untracked_files:")
    lines.extend(format_items(snapshot.git_status.untracked_files))
    lines.append("- other_files:")
    lines.extend(format_items(snapshot.git_status.other_files))
    lines.extend(
        [
            "",
            "## 已验证",
            "",
            "- 由当前执行者补充本轮已经完成的验证命令。",
            "",
            "## 未验证",
            "",
            "- 由当前执行者补充尚未执行或无法覆盖的验证范围。",
            "",
            "## 风险",
            "",
            "- 如工作区包含非本轮改动，后续执行者不要覆盖。",
            "",
            "## 下一步",
            "",
            "1. 对照 docs/harness-engineering/core/verification-matrix.md 选择验证命令。",
            "2. 更新 LOGBOOK.md 和项目进度与配置清单.md。",
            "3. 若出现可复用教训，更新 docs/harness-engineering/core/mistake-ledger.md。",
            "",
            "## 参考入口",
            "",
        ]
    )
    lines.extend(f"- {entry}" for entry in snapshot.reference_entries)
    lines.append("")
    return "\n".join(lines)


def format_items(items: tuple[str, ...]) -> list[str]:
    if not items:
        return ["  - none"]
    return [f"  - {item}" for item in items]


def resolve_output_path(output: str, root_dir: Path = ROOT_DIR) -> Path:
    timestamp = datetime.now(timezone.utc).strftime(OUTPUT_TIMESTAMP_FORMAT)
    expanded = output.replace(OUTPUT_TIMESTAMP_PLACEHOLDER, timestamp)
    path = Path(expanded)
    return path if path.is_absolute() else root_dir / path


def write_output(path: Path, content: str) -> None:
    if path.exists():
        raise FileExistsError(f"output file already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(UTF8_BOM + content.encode("utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 Harness 交接快照")
    parser.add_argument("--trace-id", default="manual-harness-snapshot")
    parser.add_argument("--goal", default="记录当前任务状态和后续交接信息")
    parser.add_argument("--status", default="in_progress", help="当前任务状态")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--output", help="写入文件，支持 {timestamp}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot = build_snapshot(
        trace_id=args.trace_id,
        goal=args.goal,
        current_status=args.status,
    )
    if args.json:
        content = json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n"
    else:
        content = format_markdown(snapshot)
    if args.output:
        try:
            write_output(resolve_output_path(args.output), content)
        except FileExistsError as exc:
            print(f"[harness-snapshot] {exc}")
            return 1
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
