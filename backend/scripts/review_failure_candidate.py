"""错误候选人工 review 命令。

- reject/defer：只生成 review 记录文件，不修改根目录 `ERRORS.md`。
- accept：必须提供正式账本字段，经临时内容校验后一次性写入 `ERRORS.md`，
  生成新的 `M-YYYYMMDD-NNN` 条目；候选文件本身不可覆盖、不可篡改。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

try:
    from check_mistake_ledger import check_ledger
    from harness_failure_candidate import (
        SCHEMA_VERSION,
        validate_candidate,
    )
except ModuleNotFoundError:
    from scripts.check_mistake_ledger import check_ledger  # type: ignore[no-redef]
    from scripts.harness_failure_candidate import (  # type: ignore[no-redef]
        SCHEMA_VERSION,
        validate_candidate,
    )

ROOT_DIR = Path(__file__).resolve().parents[2]
REVIEW_TYPE = "failure_candidate_review"
ALLOWED_DECISIONS = frozenset({"accept", "reject", "defer"})
ENTRY_HEADING_RE = re.compile(r"^##\s+(M-\d{8}-\d{3})", re.MULTILINE)
CURRENT_ENTRIES_HEADING = "## 当前条目"
# accept 入账必需的正式账本字段；缺失时拒绝写入 ERRORS.md。
REQUIRED_ACCEPT_FIELDS = (
    "root_cause",
    "impact",
    "fix",
    "new_guardrail",
    "verification",
    "next_time_signal",
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _resolve_within_root(path: Path, root_dir: Path) -> Path:
    """校验路径位于仓库根目录内，拒绝路径越界。"""
    resolved_root = root_dir.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError(f"路径越界，必须位于仓库根目录内: {path}")
    return resolved_path


def _load_candidate(path: Path, root_dir: Path) -> dict[str, Any]:
    resolved = _resolve_within_root(path, root_dir)
    if not resolved.is_file():
        raise ValueError(f"候选文件不存在: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"候选文件根节点必须是对象: {resolved}")
    issues = validate_candidate(payload)
    if issues:
        raise ValueError("候选校验失败: " + "；".join(issues))
    if payload["status"] != "pending":
        raise ValueError(f"候选状态不是 pending，禁止重复 review: {payload['status']}")
    return payload


def next_entry_id(ledger_content: str, first_seen: str) -> str:
    """扫描 ERRORS.md 现有当天序号并递增，不复用 candidate ID。"""
    date_key = first_seen.replace("-", "")
    pattern = re.compile(rf"^##\s+M-{date_key}-(\d{{3}})", re.MULTILINE)
    existing = [int(match.group(1)) for match in pattern.finditer(ledger_content)]
    next_number = (max(existing) + 1) if existing else 1
    return f"M-{date_key}-{next_number:03d}"


def _entry_markdown(
    *,
    entry_id: str,
    title: str,
    candidate: dict[str, Any],
    first_seen: str,
    fields: dict[str, str],
    linked_files: list[str],
) -> str:
    lines = [
        f"## {entry_id}：{title}",
        "",
        f"- status: {fields['status']}",
        f"- first_seen: {first_seen}",
        f"- severity: {fields['severity']}",
        f"- symptom: {fields['symptom']}",
        f"- root_cause: {fields['root_cause']}",
        f"- impact: {fields['impact']}",
        f"- fix: {fields['fix']}",
        f"- new_guardrail: {fields['new_guardrail']}",
        f"- verification: {fields['verification']}",
        f"- linked_trace: {fields['linked_trace']}",
        f"- linked_files: {'; '.join(linked_files)}",
        f"- next_time_signal: {fields['next_time_signal']}",
        f"- fingerprint: {candidate['fingerprint']}",
        f"- candidate_ref: {candidate['candidate_id']}",
        "",
    ]
    return "\n".join(lines)


def _insert_entry(ledger_content: str, entry_markdown: str) -> str:
    """优先插入“当前条目”区；没有该区时追加到文件末尾。"""
    heading_pos = ledger_content.find(CURRENT_ENTRIES_HEADING)
    if heading_pos < 0:
        base = ledger_content.rstrip("\n")
        return (base + "\n\n\n" + entry_markdown) if base else entry_markdown
    insert_at = ledger_content.find("\n", heading_pos) + 1
    return (
        ledger_content[:insert_at] + "\n" + entry_markdown + ledger_content[insert_at:]
    )


def prepare_accept_entry(
    candidate: dict[str, Any],
    *,
    operator: str,
    reason: str,
    root_dir: Path,
    ledger_path: Path | None = None,
    first_seen: str | None = None,
    title: str | None = None,
    severity: str = "medium",
    fields: dict[str, str] | None = None,
    override_duplicate: bool = False,
) -> tuple[str, str]:
    """准备 accept 入账内容：全部校验通过后返回 (新账本全文, 条目 ID)。

    本函数不修改 ERRORS.md，也不生成 review 记录；调用方必须先写 review
    记录、再提交账本，保证失败时不会出现"命令失败但账本已变更"。
    """
    values = fields or {}
    missing = [
        name for name in REQUIRED_ACCEPT_FIELDS if not values.get(name, "").strip()
    ]
    if missing:
        raise ValueError("accept 缺少正式账本字段: " + ", ".join(missing))
    if not operator.strip():
        raise ValueError("operator 不能为空")
    if not reason.strip():
        raise ValueError("reason 不能为空")
    if candidate.get("duplicate_of") and not override_duplicate:
        raise ValueError(
            f"候选已标记重复 duplicate_of={candidate['duplicate_of']}，"
            "默认禁止再次 accept；确需覆盖请提供 override_duplicate 及理由"
        )
    resolved_root = root_dir.resolve()
    ledger = ledger_path or (resolved_root / "ERRORS.md")
    if not ledger.is_file():
        raise ValueError(f"错误账本不存在: {ledger}")
    first_seen_value = first_seen or datetime.now().strftime("%Y-%m-%d")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", first_seen_value):
        raise ValueError(f"first_seen 必须是 YYYY-MM-DD: {first_seen_value}")
    if severity not in {"low", "medium", "high", "critical"}:
        raise ValueError(f"severity 非法: {severity}")
    ledger_content = ledger.read_text(encoding="utf-8")
    entry_id = next_entry_id(ledger_content, first_seen_value)
    if re.search(rf"^##\s+{re.escape(entry_id)}", ledger_content, re.MULTILINE):
        raise ValueError(f"账本已存在同 ID 条目: {entry_id}")
    linked_trace = str(
        candidate.get("trace_id") or candidate.get("run_id") or "unknown"
    )
    entry_markdown = _entry_markdown(
        entry_id=entry_id,
        title=(title or candidate["summary"]).strip().splitlines()[0],
        candidate=candidate,
        first_seen=first_seen_value,
        fields={
            "status": "open",
            "severity": severity,
            "symptom": str(candidate.get("symptom") or candidate["summary"]),
            "root_cause": values["root_cause"].strip(),
            "impact": values["impact"].strip(),
            "fix": values["fix"].strip(),
            "new_guardrail": values["new_guardrail"].strip(),
            "verification": values["verification"].strip(),
            "linked_trace": linked_trace,
            "next_time_signal": values["next_time_signal"].strip(),
        },
        linked_files=list(candidate.get("evidence_files") or []),
    )
    new_content = _insert_entry(ledger_content, entry_markdown)
    # 临时内容校验：失败不留半条正式条目。
    temp_check = (
        resolved_root.parent / ".tmp-failure-candidate-review" / "ERRORS.check.md"
    )
    temp_check.parent.mkdir(parents=True, exist_ok=True)
    temp_check.write_text(new_content, encoding="utf-8")
    try:
        result = check_ledger(temp_check)
        if not result.passed:
            raise ValueError("入账内容校验失败: " + "；".join(result.issues))
    finally:
        temp_check.unlink(missing_ok=True)
        try:
            temp_check.parent.rmdir()
        except OSError:
            pass
    return new_content, entry_id


def commit_accept(
    new_content: str,
    *,
    ledger_path: Path,
    review_path: Path,
) -> None:
    """按固定顺序提交 accept：先 review 记录，后正式账本。

    review 记录写入失败时账本保持原样；账本写入失败时回滚本轮新建的
    review 记录，保证两个文件同时成功或同时不变。
    """
    if not review_path.exists():
        raise ValueError("commit_accept 要求 review 记录已写入")
    try:
        ledger_path.write_text(new_content, encoding="utf-8")
    except OSError:
        # 账本写入失败：回滚本轮新建的 review 记录，恢复入账前状态。
        review_path.unlink(missing_ok=True)
        raise


def _write_review_file(
    candidate_path: Path,
    candidate: dict[str, Any],
    record: dict[str, Any],
) -> Path:
    """候选文件不可覆盖：review 结果写入新的 review 记录文件。"""
    review_path = candidate_path.parent / f"{candidate['candidate_id']}.review.json"
    if review_path.exists():
        raise FileExistsError(f"拒绝覆盖已有 review 记录: {review_path}")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "review_type": REVIEW_TYPE,
        "candidate_id": candidate["candidate_id"],
        "candidate_fingerprint": candidate["fingerprint"],
        "candidate_file": candidate_path.name,
        **record,
    }
    review_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return review_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="人工确认错误候选")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--decision", required=True, choices=sorted(ALLOWED_DECISIONS))
    parser.add_argument("--operator", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--root-dir", type=Path, default=ROOT_DIR)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--first-seen", help="YYYY-MM-DD；缺省为今天")
    parser.add_argument("--title", help="正式条目标题；缺省使用候选 summary")
    parser.add_argument(
        "--severity", choices=["low", "medium", "high", "critical"], default="medium"
    )
    for field_name in REQUIRED_ACCEPT_FIELDS:
        parser.add_argument(f"--{field_name.replace('_', '-')}")
    parser.add_argument("--override-duplicate", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        candidate = _load_candidate(Path(args.candidate), Path(args.root_dir))
        record: dict[str, Any] = {
            "decision": args.decision,
            "operator": args.operator.strip(),
            "reviewed_at": utc_now(),
            "reason": args.reason.strip(),
        }
        if not record["operator"]:
            raise ValueError("operator 不能为空")
        if not record["reason"]:
            raise ValueError("reason 不能为空")
        ledger_path = args.ledger or Path(args.root_dir).resolve() / "ERRORS.md"
        new_content = ""
        if record["decision"] == "accept":
            values = {
                name: getattr(args, name) or "" for name in REQUIRED_ACCEPT_FIELDS
            }
            # 先准备并通过临时内容校验，此时账本与 review 记录均未被修改。
            new_content, entry_id = prepare_accept_entry(
                candidate,
                operator=record["operator"],
                reason=record["reason"],
                root_dir=Path(args.root_dir),
                ledger_path=args.ledger,
                first_seen=args.first_seen,
                title=args.title,
                severity=args.severity,
                fields=values,
                override_duplicate=args.override_duplicate,
            )
            record["ledger_entry_id"] = entry_id
            record["entry_id"] = entry_id
        # 原子顺序：先写 review 记录（已存在则整体失败），再提交正式账本。
        review_path = _write_review_file(Path(args.candidate), candidate, record)
        if record["decision"] == "accept":
            commit_accept(new_content, ledger_path=ledger_path, review_path=review_path)
    except (OSError, ValueError, FileExistsError) as exc:
        print(f"[failure-candidate-review] FAIL {exc}", file=sys.stderr)
        return 1
    if args.print_summary:
        print(
            f"failure_candidate_review decision={record['decision']} "
            f"candidate_id={candidate['candidate_id']} "
            f"entry_id={record.get('entry_id') or 'none'}"
        )
    else:
        print(
            f"[failure-candidate-review] PASS decision={record['decision']} "
            f"candidate_id={candidate['candidate_id']}"
        )
    print(f"review_file={review_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
