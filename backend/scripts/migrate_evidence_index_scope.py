#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 evidence-index.md 迁移到不可变 git blob 证据模型（B1.6 → B1.9）。

对每个证据条目做一次性机械迁移：
1. `file` 引用统一为工件级前缀（repo:/local:/production:/external:/git:）。
2. 补充 `storage_scope`（条目级摘要字段）与 `commit_sha`（条目绑定提交）。
3. **`repo:<path>` 转换为 `git:<commit>:<path>`**：commit 为该条目引入提交
   （已有 `commit_sha` 字段则沿用），sha256 取该提交下 git blob 内容的
   sha256——绑定不可变提交，之后**禁止以当前工作树刷新历史哈希**。

幂等：已有 commit_sha 且引用已全部为 git:/local:/production:/external: 且
sha256 已存在的条目不重复处理（不会覆盖既有哈希）。
运行：python scripts/migrate_evidence_index_scope.py [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = ROOT_DIR / "docs" / "harness-engineering" / "core" / "evidence-index.md"
INDEX_REL = "docs/harness-engineering/core/evidence-index.md"
ENTRY_HEADING_RE = re.compile(r"^##\s+(E-\d{8}-\d{3})：(.+)$")
FILE_REFERENCE_RE = re.compile(r"`([^`]+)`")
REFERENCE_PREFIXES = ("repo:", "local:", "production:", "external:", "git:")
REGISTRY_REL = INDEX_REL
LEGACY_FILE_ALIASES = {
    "app/service/wecom/employee_agent_reply_guard.py": "app/service/wecom/employee_agent_mixed_reply.py",
    "app/service/wecom/employee_agent_order_list_guard.py": "app/service/wecom/intelligent_bot_order_lookup.py",
    "app/service/wecom/employee_agent_llm_plan.py": "app/service/wecom/employee_agent_planner.py",
    "tests/service/test_miniapp_order.py": "tests/service/test_order.py",
    "tests/service/test_miniapp_chat.py": "tests/api/test_miniapp_chat_api.py",
    "tests/service/llm": "tests/service/test_llm_provider.py",
    "tests/service/agents": "tests/service/agents/test_llm_factory.py",
}

_GIT_BLOB_CACHE: dict[str, str] = {}


def _git(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT_DIR,
        capture_output=True,
    )


def _find_entry_commit(entry_id: str, index_rel: str) -> str | None:
    """查找引入该条目（entry id）的提交：git log -S 限定索引文件，取最早一条。"""
    proc = _git(
        [
            "log",
            "--reverse",
            "--format=%H",
            "-S",
            entry_id,
            "--",
            index_rel,
        ]
    )
    if proc.returncode != 0:
        return None
    for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
        if line.strip():
            return line.strip()
    return None


def _git_blob_sha256(commit: str, rel: str) -> str | None:
    """按 `commit:rel` 读取 git blob 内容并计算 sha256。"""
    commit_path = f"{commit}:{rel}"
    if commit_path in _GIT_BLOB_CACHE:
        return _GIT_BLOB_CACHE[commit_path] or None
    proc = _git(["cat-file", "blob", commit_path])
    if proc.returncode != 0:
        _GIT_BLOB_CACHE[commit_path] = ""
        return None
    digest = hashlib.sha256(proc.stdout).hexdigest()
    _GIT_BLOB_CACHE[commit_path] = digest
    return digest


def _last_commit_for_path(rel: str) -> str | None:
    """最后一次修改该路径的提交（回退绑定用）。"""
    proc = _git(["log", "--format=%H", "-1", "--", rel])
    if proc.returncode != 0:
        return None
    for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
        if line.strip():
            return line.strip()
    return None


def _prefix_reference(reference: str) -> str:
    norm = reference.strip()
    forward = norm.replace("\\", "/")
    if forward.startswith(("http://", "https://")):
        return norm
    if forward.startswith(REFERENCE_PREFIXES):
        scope = forward.split(":", 1)[0]
        rel = forward.split(":", 1)[1].lstrip("/").replace("\\", "/")
        if scope == "repo" and rel.startswith("reports/"):
            return f"local:{rel}"
        return norm
    match = re.match(r"^[A-Za-z]:/Project/YunxiBakeBot/(.*)$", forward)
    if match:
        rel = match.group(1).lstrip("/")
        if rel.startswith("reports/"):
            return f"local:{rel}"
        return f"repo:{rel}"
    if forward.startswith("/opt/"):
        return f"production:{forward}"
    if forward.startswith("/") or re.match(r"^[A-Za-z]:/", forward):
        return f"external:{forward}"
    if norm:
        bare = norm.replace(chr(92), "/")
        if bare.startswith("reports/"):
            return f"local:{bare}"
        return f"repo:{bare}"
    return norm


def _scope_for_references(references: list[str]) -> str:
    for prefix, scope in (
        ("production:", "production"),
        ("git:", "repository"),
        ("repo:", "repository"),
        ("local:", "local"),
        ("external:", "external"),
    ):
        if any(ref.startswith(prefix) for ref in references):
            return scope
    return "external"


def _bind_repo_ref_to_commit(reference: str, commit: str) -> str:
    """把 `repo:<rel>` 绑定到 `git:<commit>:<rel>`。

    文件在条目引入提交中不存在时按别名 / 最后修改提交回退；仍不存在（未跟踪
    的本地调试文件）降级为 `local:<rel>`（gitignore 语义，哈希可选）。
    """
    rel = reference.split(":", 1)[1].lstrip("/").replace("\\", "/")
    if rel == REGISTRY_REL:
        return reference
    candidates = [rel, LEGACY_FILE_ALIASES.get(rel, rel)]
    for candidate in dict.fromkeys(candidates):
        if _git_blob_sha256(commit, candidate) is not None:
            return f"git:{commit}:{candidate}"
    fallback = _last_commit_for_path(rel)
    if fallback:
        for candidate in dict.fromkeys(candidates):
            if _git_blob_sha256(fallback, candidate) is not None:
                return f"git:{fallback}:{candidate}"
    return f"local:{rel}"


def _transform_file_field(value: str, commit: str) -> tuple[str, list[str]]:
    refs = FILE_REFERENCE_RE.findall(value)
    replaced: dict[str, str] = {}
    for ref in refs:
        if ref in replaced:
            continue
        prefixed = _prefix_reference(ref)
        if prefixed.startswith("repo:") and commit:
            prefixed = _bind_repo_ref_to_commit(prefixed, commit)
        replaced[ref] = prefixed
    for old, new in replaced.items():
        value = value.replace(f"`{old}`", f"`{new}`")
    return value, list(replaced.values())


def _hash_git_refs(references: list[str], commit: str) -> list[tuple[str, str]]:
    """为绑定到给定提交的 git: 文件引用计算 blob sha256，返回 (rel, digest)。"""
    hashed: list[tuple[str, str]] = []
    for reference in references:
        if not reference.startswith("git:"):
            continue
        rest = reference.split(":", 1)[1]
        ref_commit, sep, rel = rest.partition(":")
        if not sep or not ref_commit or not rel or rel == REGISTRY_REL:
            continue
        digest = _git_blob_sha256(ref_commit, rel)
        if digest is not None:
            hashed.append((rel, digest))
    return hashed


def _format_hashes(hashed: list[tuple[str, str]]) -> str | None:
    if not hashed:
        return None
    if len(hashed) == 1:
        return hashed[0][1]
    return "；".join(f"{rel}={digest}" for rel, digest in hashed)


def _entry_commit(lines: list[str], entry_id: str, index_rel: str) -> str | None:
    """条目绑定提交：已有 commit_sha 字段沿用，否则查引入提交。"""
    for line in lines:
        m = re.match(r"^-\s+commit_sha:\s*([0-9a-f]{40,64})\s*$", line)
        if m:
            return m.group(1)
    return _find_entry_commit(entry_id, index_rel)


def _process_entry(
    lines: list[str], entry_id: str, index_rel: str
) -> tuple[list[str], int]:
    """迁移单个条目行块，返回 (新行, 修改计数)。"""
    changes = 0
    file_field_idx = next(
        (i for i, line in enumerate(lines) if re.match(r"^-\s+file:", line)), None
    )
    if file_field_idx is None:
        return lines, changes

    commit = _entry_commit(lines, entry_id, index_rel)
    raw_value = re.sub(r"^-\s+file:\s*", "", lines[file_field_idx])
    new_value, refs = _transform_file_field(raw_value, commit or "")
    if new_value != raw_value:
        lines[file_field_idx] = f"- file: {new_value}"
        changes += 1

    prefixed_refs = [
        ref.strip().replace("\\", "/")
        for ref in refs
        if not ref.strip().startswith(("http://", "https://"))
    ]

    if not any(line.startswith("- storage_scope:") for line in lines):
        scope = _scope_for_references(prefixed_refs)
        lines.append(f"- storage_scope: {scope}")
        changes += 1

    if commit and not any(line.startswith("- commit_sha:") for line in lines):
        lines.append(f"- commit_sha: {commit}")
        changes += 1

    if commit:
        commit_map: dict[str, str] = {}
        for ref in prefixed_refs:
            if not ref.startswith("git:"):
                continue
            rest = ref.split(":", 1)[1]
            ref_commit, sep2, rel = rest.partition(":")
            if sep2 and ref_commit != commit and rel != REGISTRY_REL:
                commit_map[rel] = ref_commit
        map_line = None
        if commit_map:
            map_line = "- commit_map: " + "；".join(
                f"{rel}={c}" for rel, c in commit_map.items()
            )
        map_idx = next(
            (i for i, line in enumerate(lines) if line.startswith("- commit_map:")),
            None,
        )
        if map_line is None:
            if map_idx is not None:
                del lines[map_idx]
                changes += 1
        elif map_idx is None:
            lines.append(map_line)
            changes += 1
        elif lines[map_idx] != map_line:
            lines[map_idx] = map_line
            changes += 1

    if commit:
        hashed = _hash_git_refs(prefixed_refs, commit)
        sha_index = next(
            (i for i, line in enumerate(lines) if line.startswith("- sha256:")),
            None,
        )
        if sha_index is None:
            if hashed:
                lines.append(f"- sha256: {_format_hashes(hashed)}")
                changes += 1
        else:
            existing = re.sub(r"^-\s+sha256:\s*", "", lines[sha_index])
            merged = _format_hashes(hashed)
            if merged and merged != existing:
                lines[sha_index] = f"- sha256: {merged}"
                changes += 1
    return lines, changes


def migrate(path: Path = DEFAULT_INDEX, *, dry_run: bool = False) -> int:
    path = Path(path)
    if not path.exists():
        print(f"[migrate-evidence] FAIL：找不到索引 {path}", file=sys.stderr)
        return 1
    index_rel = path.resolve().relative_to(ROOT_DIR.resolve()).as_posix()
    text = path.read_text(encoding="utf-8-sig")
    out_lines: list[str] = []
    current: list[str] = []
    total_changes = 0
    entry_count = 0

    for raw_line in text.splitlines():
        raw_line = raw_line.removeprefix("\ufeff")
        if ENTRY_HEADING_RE.match(raw_line):
            if current:
                entry_count += 1
                new_lines, changes = _process_entry(
                    current, ENTRY_HEADING_RE.match(current[0]).group(1), index_rel
                )
                total_changes += changes
                out_lines.extend(new_lines)
            current = [raw_line]
        elif re.match(r"^##\s+", raw_line):
            if current:
                entry_count += 1
                new_lines, changes = _process_entry(
                    current, ENTRY_HEADING_RE.match(current[0]).group(1), index_rel
                )
                total_changes += changes
                out_lines.extend(new_lines)
            current = []
            out_lines.append(raw_line)
        elif current:
            current.append(raw_line)
        else:
            out_lines.append(raw_line)
    if current:
        entry_count += 1
        new_lines, changes = _process_entry(
            current, ENTRY_HEADING_RE.match(current[0]).group(1), index_rel
        )
        total_changes += changes
        out_lines.extend(new_lines)

    print(
        f"[migrate-evidence] 条目 {entry_count}，修改行 {total_changes}"
        + ("（dry-run，未写回）" if dry_run else "")
    )
    if dry_run:
        return 0
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="迁移 evidence index 到不可变 git blob 模型"
    )
    parser.add_argument("--path", default=str(DEFAULT_INDEX), help="索引路径")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写回")
    return parser


if __name__ == "__main__":
    raise SystemExit(migrate(**vars(build_parser().parse_args())))
