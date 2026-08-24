#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 .secrets.baseline 未被意外改写，并强制受控更新流程。

detect-secrets 的 `--baseline` 验证路径在部分版本会原地重写 baseline。
本守卫在 detect-secrets 钩子之后运行，检查三方状态：

1. worktree 相对 index 的未暂存污染（detect-secrets 意外改写）→ 阻断。
2. index 相对 HEAD 的已暂存变更 → 必须同时满足，否则阻断：
   - 受控记录文件 `docs/harness-engineering/core/secrets-baseline-changes.md`
     也已随同一提交暂存（记录必须从 git index 读取，只改工作区不算）；
   - 记录包含完整字段 `old_sha256 / new_sha256 / command / version / trace_id /
     approved_by`；
   - 记录中的 (old_sha256, new_sha256) 精确绑定本次 HEAD→index 哈希对；
   - 该记录必须为本次新增记录，不得复用历史已提交记录。
3. 任一 git 命令失败按阻断处理，不允许静默通过。

受控更新流程：候选副本生成 -> diff/哈希校验 -> 人工批准 -> 登记记录并
`git add` 记录文件与 `.secrets.baseline`（同一提交）。
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BASELINE_REL = ".secrets.baseline"
CHANGES_LOG_REL = "docs/harness-engineering/core/secrets-baseline-changes.md"
CHANGES_LOG = ROOT_DIR / CHANGES_LOG_REL

REQUIRED_RECORD_FIELDS = (
    "old_sha256",
    "new_sha256",
    "command",
    "version",
    "trace_id",
    "approved_by",
)
HASH_RE = re.compile(r"[0-9a-f]{64}")


class _GitFailure(Exception):
    """Git 环境不可用或命令异常，视为阻断。"""


def _git_probe() -> None:
    """确认 git 可用且 ROOT_DIR 是 Git 仓库；否则抛 _GitFailure。"""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise _GitFailure("git 命令不可用") from exc
    if proc.returncode != 0 or "true" not in proc.stdout.strip().lower():
        raise _GitFailure(f"目录不是 Git 仓库：{proc.stderr.strip()!r}")


def _git(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT_DIR,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise _GitFailure("git 命令不可用") from exc


def _sha256(data: bytes | None) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def _git_show(expr: str) -> bytes | None:
    """按引用读取文件内容；引用中不存在（git show 128）时返回 None。

    其他非 0 返回码一律视为 Git 异常（阻断），不允许静默吞掉。
    """
    proc = _git(["show", expr])
    if proc.returncode == 0:
        return proc.stdout
    if proc.returncode == 128:
        return None
    raise _GitFailure(f"git show {expr} 失败（rc={proc.returncode}）：{proc.stderr!r}")


def _git_has_unstaged(path: str) -> bool:
    """worktree 相对 index 是否有未暂存改动。git 仅允许返回 0（无差异）/ 1（有差异）。"""
    proc = _git(["diff", "--quiet", "--", path])
    if proc.returncode in (0, 1):
        return proc.returncode == 1
    raise _GitFailure(
        f"git diff（未暂存检查）失败（rc={proc.returncode}）：{proc.stderr!r}"
    )


def _git_has_staged(path: str) -> bool:
    """index 相对 HEAD 是否有已暂存改动。git 仅允许返回 0（无差异）/ 1（有差异）。"""
    proc = _git(["diff", "--cached", "--quiet", "--", path])
    if proc.returncode in (0, 1):
        return proc.returncode == 1
    raise _GitFailure(
        f"git diff --cached（已暂存检查）失败（rc={proc.returncode}）：{proc.stderr!r}"
    )


def _parse_records(text: str) -> list[dict[str, str]]:
    """解析受控记录文件，按 `## [日期]` 分块，返回字段字典列表。"""
    records: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        if re.match(r"^##\s+\[", line):
            if current is not None:
                records.append(current)
            current = {}
            continue
        if current is None:
            continue
        m = re.match(r"^-\s+([a-z0-9_]+):\s*(.*)$", line)
        if m:
            current[m.group(1)] = m.group(2).strip()
    if current is not None:
        records.append(current)
    return records


def _is_complete_record(record: dict[str, str]) -> bool:
    """记录必须含全部必填字段，且两枚哈希为 64 位 hex。"""
    if not all(record.get(field) for field in REQUIRED_RECORD_FIELDS):
        return False
    return bool(HASH_RE.fullmatch(record.get("old_sha256", ""))) and bool(
        HASH_RE.fullmatch(record.get("new_sha256", ""))
    )


def _main() -> int:
    # 0) git 可用性探针（非仓库 / git 缺失按阻断处理）
    _git_probe()

    # 1) worktree vs index：未暂存污染
    if _git_has_unstaged(BASELINE_REL):
        print(
            "[secrets-baseline] FAIL：.secrets.baseline 相对 index 存在未暂存改动。"
            "若为 detect-secrets 意外触发，执行 `git checkout -- .secrets.baseline` 恢复；"
            "若为有意更新，请按受控流程（候选副本 -> diff/哈希 -> 人工批准 -> 记录 -> git add）。",
            file=sys.stderr,
        )
        return 1

    # 2) index vs HEAD：无已暂存变更则通过
    if not _git_has_staged(BASELINE_REL):
        print("[secrets-baseline] OK：.secrets.baseline 状态一致且符合受控流程")
        return 0

    head_sha = _sha256(_git_show(f"HEAD:{BASELINE_REL}"))
    index_sha = _sha256(_git_show(f":0:{BASELINE_REL}"))
    if head_sha == index_sha:
        print(
            "[secrets-baseline] FAIL：index 与 HEAD 哈希相同但存在暂存差异，状态异常",
            file=sys.stderr,
        )
        return 1

    # 3) 受控记录必须随同一提交暂存
    if not _git_has_staged(CHANGES_LOG_REL):
        print(
            "[secrets-baseline] FAIL：.secrets.baseline 存在已暂存变更，但受控记录文件"
            f"`{CHANGES_LOG_REL}` 未随同一提交暂存（仅修改工作区不算）。"
            "请在 docs/harness-engineering/core/secrets-baseline-changes.md 登记 "
            "old_sha256/new_sha256/command/version/trace_id/approved_by，"
            "并 `git add` 记录文件与 .secrets.baseline 后一起提交。",
            file=sys.stderr,
        )
        return 1

    # 4) 从 index 读取记录（而非 worktree），匹配本次哈希对并校验完整字段
    index_log = _git_show(f":0:{CHANGES_LOG_REL}")
    head_log = _git_show(f"HEAD:{CHANGES_LOG_REL}")
    index_records = _parse_records((index_log or b"").decode("utf-8"))
    head_pairs = {
        (record.get("old_sha256"), record.get("new_sha256"))
        for record in _parse_records((head_log or b"").decode("utf-8"))
        if _is_complete_record(record)
    }

    matched: dict[str, str] | None = None
    for record in index_records:
        if not _is_complete_record(record):
            continue
        if record["old_sha256"] == head_sha and record["new_sha256"] == index_sha:
            matched = record
            break

    if matched is None:
        print(
            "[secrets-baseline] FAIL：未找到完整字段且与本次 HEAD→index 哈希对"
            f"（{head_sha[:12]}.. → {index_sha[:12]}..）匹配的受控记录。"
            "请登记完整字段 old_sha256/new_sha256/command/version/trace_id/approved_by。",
            file=sys.stderr,
        )
        return 1

    if (head_sha, index_sha) in head_pairs:
        print(
            "[secrets-baseline] FAIL：本次哈希对对应的记录已存在于历史提交，"
            "禁止复用历史记录作为本次变更的批准。请按受控流程新增一条记录。",
            file=sys.stderr,
        )
        return 1

    print("[secrets-baseline] OK：.secrets.baseline 状态一致且符合受控流程")
    return 0


def main() -> int:
    try:
        return _main()
    except _GitFailure as exc:
        print(f"[secrets-baseline] FAIL：Git 校验异常：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
