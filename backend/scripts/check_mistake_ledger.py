"""检查 mistake ledger 结构是否可机器读取。"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LEDGER = (
    ROOT_DIR / "docs" / "harness-engineering" / "core" / "mistake-ledger.md"
)
ENTRY_HEADING_RE = re.compile(r"^##\s+(M-\d{8}-\d{3})：(.+)$")
FIELD_RE = re.compile(r"^-\s+([a-z_]+):\s*(.*)$")
REQUIRED_FIELDS = (
    "status",
    "first_seen",
    "severity",
    "symptom",
    "root_cause",
    "impact",
    "fix",
    "new_guardrail",
    "verification",
    "linked_trace",
    "linked_files",
    "next_time_signal",
)
ALLOWED_STATUS = frozenset({"open", "guarded", "verified"})
ALLOWED_SEVERITY = frozenset({"low", "medium", "high", "critical"})
EMPTY_LEDGER_MARKER = "暂无正式条目"


@dataclass(frozen=True)
class LedgerEntry:
    entry_id: str
    title: str
    fields: dict[str, str]


@dataclass(frozen=True)
class LedgerCheckResult:
    passed: bool
    entries: tuple[LedgerEntry, ...]
    issues: tuple[str, ...]


def parse_entries(content: str) -> tuple[LedgerEntry, ...]:
    entries: list[LedgerEntry] = []
    current_id = ""
    current_title = ""
    current_fields: dict[str, str] = {}
    for raw_line in content.splitlines():
        heading_match = ENTRY_HEADING_RE.match(raw_line)
        if heading_match:
            if current_id:
                entries.append(
                    LedgerEntry(current_id, current_title, dict(current_fields))
                )
            current_id = heading_match.group(1)
            current_title = heading_match.group(2).strip()
            current_fields = {}
            continue
        if not current_id:
            continue
        field_match = FIELD_RE.match(raw_line)
        if field_match:
            current_fields[field_match.group(1)] = field_match.group(2).strip()
    if current_id:
        entries.append(LedgerEntry(current_id, current_title, dict(current_fields)))
    return tuple(entries)


def validate_entry(entry: LedgerEntry) -> list[str]:
    issues: list[str] = []
    for field_name in REQUIRED_FIELDS:
        value = entry.fields.get(field_name, "")
        if not value:
            issues.append(f"{entry.entry_id}: missing field `{field_name}`")
    status = entry.fields.get("status")
    if status and status not in ALLOWED_STATUS:
        issues.append(f"{entry.entry_id}: invalid status `{status}`")
    severity = entry.fields.get("severity")
    if severity and severity not in ALLOWED_SEVERITY:
        issues.append(f"{entry.entry_id}: invalid severity `{severity}`")
    return issues


def check_ledger(path: Path = DEFAULT_LEDGER) -> LedgerCheckResult:
    if not path.exists():
        return LedgerCheckResult(False, (), (f"ledger not found: {path}",))
    content = path.read_text(encoding="utf-8")
    entries = parse_entries(content)
    if not entries and EMPTY_LEDGER_MARKER not in content:
        return LedgerCheckResult(
            False,
            (),
            ("ledger has no entries and no empty-ledger marker",),
        )
    issues: list[str] = []
    for entry in entries:
        issues.extend(validate_entry(entry))
    return LedgerCheckResult(not issues, entries, tuple(issues))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查 mistake ledger 结构")
    parser.add_argument("--path", default=str(DEFAULT_LEDGER), help="ledger 文件路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = check_ledger(Path(args.path))
    if result.passed:
        print(f"[mistake-ledger] ok entries={len(result.entries)}")
        return 0
    print("[mistake-ledger] failed")
    for issue in result.issues:
        print(f"  - {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
