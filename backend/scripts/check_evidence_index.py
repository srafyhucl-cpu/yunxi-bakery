"""检查 Harness evidence index 结构是否可机器读取。

工件级引用与完整性合同（B1.9 口径）：
- `file` 中每个引用必须是工件级前缀 `git:/repo:/local:/production:/external:`
  或 http(s) URL，禁止裸路径（绝对或相对）。
- `git:<commit>:<path>`（B1.9 起）：仓库工件绑定**不可变提交**，按该提交的
  git blob 校验哈希；blob 缺失或 sha256 缺项/不匹配阻断。历史条目绑定其
  引入提交，禁止以当前工作树重写。
- 每个条目必须含 `storage_scope`（repository / local / production / external），
  作为**摘要字段**描述证据主要存放域；工件级 scope 以每个 `file` 引用的前缀为准，
  多存储域条目允许单一摘要值。`commit_sha`（B1.9 起）记录条目绑定提交。
- `sha256`：`git:` / `repo:` 文件工件必填并校验匹配；`local:` 工件为 gitignore
  生成物，哈希可选、仅校验格式，不强制匹配；`production:` / `external:` 不本地
  核验；`docs/harness-engineering/core/evidence-index.md` 自身按 registry 处理
  （自引用哈希必然漂移）。
- 仓内工件缺失或哈希缺项必须阻断；本地留存工件缺失仅登记不阻断。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_EVIDENCE_INDEX = (
    ROOT_DIR / "docs" / "harness-engineering" / "core" / "evidence-index.md"
)
ENTRY_HEADING_RE = re.compile(r"^##\s+(E-\d{8}-\d{3})：(.+)$")
SECOND_LEVEL_HEADING_RE = re.compile(r"^##\s+")
FIELD_RE = re.compile(r"^-\s+([a-z_][a-z0-9_]*):\s*(.*)$")
FILE_REFERENCE_RE = re.compile(r"`([^`]+)`")
LEGACY_FILE_ALIASES = {
    "app/service/wecom/employee_agent_reply_guard.py": "app/service/wecom/employee_agent_mixed_reply.py",
    "app/service/wecom/employee_agent_order_list_guard.py": "app/service/wecom/intelligent_bot_order_lookup.py",
    "app/service/wecom/employee_agent_llm_plan.py": "app/service/wecom/employee_agent_planner.py",
    "tests/service/test_miniapp_order.py": "tests/service/test_order.py",
    "tests/service/test_miniapp_chat.py": "tests/api/test_miniapp_chat_api.py",
    "tests/service/llm": "tests/service/test_llm_provider.py",
    "tests/service/agents": "tests/service/agents/test_llm_factory.py",
}
REQUIRED_FIELDS = (
    "trace_id",
    "generated_at",
    "evidence_type",
    "file",
    "command",
    "result",
    "related_logbook",
    "contains_sensitive_data",
    "retention_note",
    "storage_scope",
    "summary",
)
ALLOWED_RESULTS = frozenset({"pass", "fail", "partial", "partial-pass"})
ALLOWED_SENSITIVE_FLAGS = frozenset({"yes", "no"})
ALLOWED_EVIDENCE_STATUSES = frozenset({"active", "retired"})
ALLOWED_STORAGE_SCOPES = frozenset({"repository", "local", "production", "external"})
REFERENCE_PREFIXES = ("repo:", "local:", "production:", "external:", "git:")
PREFLIGHT_CONTRACT_EVIDENCE_ID = "E-20260706-001"
PREFLIGHT_CONTRACT_REQUIRED_SNIPPETS = (
    "check_preflight_business_contracts.py",
    "preflight-contract-check-20260706-232901.json",
    "business_contracts.static_checks",
)
# 本地留存工件：gitignore 的本地报告/证据输出。缺失（如干净 clone / CI）时不阻断，
# 仅登记名称、哈希与保留策略；仓内必需证据（repo: 引用）缺失或哈希缺项仍阻断。
LOCAL_ARTIFACT_PREFIXES = ("reports/harness",)


@dataclass(frozen=True)
class EvidenceEntry:
    entry_id: str
    title: str
    fields: dict[str, str]


@dataclass(frozen=True)
class EvidenceCheckResult:
    passed: bool
    entries: tuple[EvidenceEntry, ...]
    issues: tuple[str, ...]
    file_integrity: tuple[dict[str, str | bool], ...] = ()


def parse_entries(content: str) -> tuple[EvidenceEntry, ...]:
    entries: list[EvidenceEntry] = []
    current_id = ""
    current_title = ""
    current_fields: dict[str, str] = {}
    for raw_line in content.splitlines():
        raw_line = raw_line.removeprefix("\ufeff")
        heading_match = ENTRY_HEADING_RE.match(raw_line)
        if heading_match:
            if current_id:
                entries.append(
                    EvidenceEntry(current_id, current_title, dict(current_fields))
                )
            current_id = heading_match.group(1)
            current_title = heading_match.group(2).strip()
            current_fields = {}
            continue
        if current_id and SECOND_LEVEL_HEADING_RE.match(raw_line):
            entries.append(
                EvidenceEntry(current_id, current_title, dict(current_fields))
            )
            current_id = ""
            current_title = ""
            current_fields = {}
            continue
        if not current_id:
            continue
        field_match = FIELD_RE.match(raw_line)
        if field_match:
            current_fields[field_match.group(1)] = field_match.group(2).strip()
    if current_id:
        entries.append(EvidenceEntry(current_id, current_title, dict(current_fields)))
    return tuple(entries)


def _parse_sha256_map(text: str) -> dict[str, str]:
    """解析 sha256 映射格式 `file=sha256；file=sha256`。"""
    result: dict[str, str] = {}
    for part in text.split("；"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            key = key.strip().replace("\\", "/")
            value = value.strip()
            if re.fullmatch(r"[0-9a-f]{64}", value):
                result[key] = value
    return result


def _parse_commit_map(text: str) -> dict[str, str]:
    """解析工件级 commit 映射 `path=commit；path=commit`（40 位 hex）。"""
    result: dict[str, str] = {}
    for part in text.split("；"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            key = key.strip().replace("\\", "/")
            value = value.strip()
            if re.fullmatch(r"[0-9a-f]{40}", value):
                result[key] = value
    return result


def validate_entry(entry: EvidenceEntry) -> list[str]:
    issues: list[str] = []
    for field_name in REQUIRED_FIELDS:
        value = entry.fields.get(field_name, "")
        if not value:
            issues.append(f"{entry.entry_id}: missing field `{field_name}`")
    result = entry.fields.get("result")
    if result and result not in ALLOWED_RESULTS:
        issues.append(f"{entry.entry_id}: invalid result `{result}`")
    sensitive_flag = entry.fields.get("contains_sensitive_data")
    if sensitive_flag and sensitive_flag not in ALLOWED_SENSITIVE_FLAGS:
        issues.append(
            f"{entry.entry_id}: invalid contains_sensitive_data `{sensitive_flag}`"
        )
    evidence_status = entry.fields.get("evidence_status", "active")
    if evidence_status not in ALLOWED_EVIDENCE_STATUSES:
        issues.append(f"{entry.entry_id}: invalid evidence_status {evidence_status}")
    storage_scope = entry.fields.get("storage_scope")
    if storage_scope and storage_scope not in ALLOWED_STORAGE_SCOPES:
        issues.append(f"{entry.entry_id}: invalid storage_scope `{storage_scope}`")
    sha256 = entry.fields.get("sha256")
    is_pure_hex = bool(re.fullmatch(r"[0-9a-f]{64}", sha256 or ""))
    is_sha_map = bool(_parse_sha256_map(sha256 or ""))
    if sha256 and not is_pure_hex and not is_sha_map:
        issues.append(f"{entry.entry_id}: invalid sha256 `{sha256[:16] or sha256}`")
    for reference in FILE_REFERENCE_RE.findall(entry.fields.get("file", "")):
        norm = reference.strip().replace("\\", "/")
        if norm.startswith(("http://", "https://")):
            continue
        if norm.startswith(REFERENCE_PREFIXES):
            continue
        issues.append(
            f"{entry.entry_id}: file 引用禁止裸路径，"
            f"须使用 repo:/local:/production:/external: 前缀：`{norm}`"
        )
    evidence_status = entry.fields.get("evidence_status", "active")
    has_git_refs = any(
        ref.strip().replace("\\", "/").startswith("git:")
        for ref in FILE_REFERENCE_RE.findall(entry.fields.get("file", ""))
    )
    if has_git_refs and evidence_status != "retired":
        commit_sha = entry.fields.get("commit_sha", "")
        if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
            issues.append(
                f"{entry.entry_id}: 含 git: 工件的活动条目必须有合法 "
                f"commit_sha（完整 40 位 hex）"
            )
        elif not _is_commit_sha(commit_sha):
            issues.append(
                f"{entry.entry_id}: commit_sha `{commit_sha[:12]}..` 不是有效 "
                f"commit 对象（可变引用或不存在）"
            )
    return issues


def validate_preflight_contract_entry(entry: EvidenceEntry) -> list[str]:
    combined_text = "\n".join(entry.fields.values())
    issues: list[str] = []
    if entry.fields.get("result") != "pass":
        issues.append(f"{entry.entry_id}: preflight contract evidence result must pass")
    for snippet in PREFLIGHT_CONTRACT_REQUIRED_SNIPPETS:
        if snippet not in combined_text:
            issues.append(
                f"{entry.entry_id}: missing preflight contract reference `{snippet}`"
            )
    return issues


def validate_entries(entries: tuple[EvidenceEntry, ...]) -> list[str]:
    issues: list[str] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if entry.entry_id in seen_ids:
            issues.append(f"{entry.entry_id}: duplicate evidence id")
        seen_ids.add(entry.entry_id)
        issues.extend(validate_entry(entry))
        if entry.entry_id == PREFLIGHT_CONTRACT_EVIDENCE_ID:
            issues.extend(validate_preflight_contract_entry(entry))
    if not any(entry.entry_id == PREFLIGHT_CONTRACT_EVIDENCE_ID for entry in entries):
        issues.append(f"missing evidence entry `{PREFLIGHT_CONTRACT_EVIDENCE_ID}`")
    return issues


def _parse_reference(reference: str) -> tuple[str, str]:
    """拆解工件级引用，返回 (scope, 去前缀引用)。scope ∈ git/repo/local/production/external/url/裸路径。"""
    norm = reference.strip().replace("\\", "/")
    if norm.startswith(("http://", "https://")):
        return "url", norm
    for prefix in REFERENCE_PREFIXES:
        if norm.startswith(prefix):
            return prefix[:-1], norm.split(":", 1)[1].lstrip("/")
    return "", norm


_GIT_BLOB_CACHE: dict[str, str] = {}
_COMMIT_CACHE: dict[str, bool] = {}


class _GitCatFileBatch:
    """`git cat-file --batch` 单进程批量读取器（B3：替代逐条启动 git 子进程）。

    全部查询经同一个子进程的 stdin/stdout 管道往返，进程只启动一次：
    - blob 查询：输入 `<commit>:<path>`，读取 `<sha> blob <size>` 头与内容，返回内容 sha256；
    - commit 校验：输入完整 40 位 `<sha>`，读取 `<sha> commit <size>` 头即视为合法 commit；
    - 对象缺失时 git 输出 `<输入> missing`，返回 None。
    结果按表达式缓存，避免重复往返。
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen[bytes] | None = None
        self._blob_cache: dict[str, str] = {}
        self._commit_cache: dict[str, bool] = {}

    def _ensure_proc(self) -> subprocess.Popen[bytes] | None:
        if self._proc is not None:
            return self._proc
        try:
            self._proc = subprocess.Popen(
                ["git", "cat-file", "--batch"],
                cwd=ROOT_DIR,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
        except (FileNotFoundError, OSError):
            self._proc = None
        return self._proc

    def close(self) -> None:
        """关闭批处理子进程；未启动或无进程时为空操作。"""
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    def _query(self, expr: str) -> tuple[str, bytes | None]:
        """发送一行查询，返回（头部行，内容字节）；内容为 None 表示缺失或不可用。"""
        proc = self._ensure_proc()
        if proc is None or proc.stdin is None or proc.stdout is None:
            return "", None
        try:
            proc.stdin.write(expr.encode("utf-8", "surrogateescape") + b"\n")
            proc.stdin.flush()
            header_line = proc.stdout.readline()
        except (BrokenPipeError, OSError):
            self.close()
            return "", None
        if not header_line:
            self.close()
            return "", None
        header = header_line.decode("utf-8", "replace").rstrip("\n")
        parts = header.split(" ")
        if len(parts) == 2 and parts[1] == "missing":
            return header, None
        if len(parts) != 3:
            return header, None
        try:
            size = int(parts[2])
        except ValueError:
            return header, None
        try:
            content = proc.stdout.read(size)
            trailing = proc.stdout.read(1)
        except OSError:
            self.close()
            return header, None
        if len(content) != size or trailing != b"\n":
            self.close()
            return header, None
        return header, content

    def blob_sha256(self, commit_path: str) -> str | None:
        """按 `git:<commit>:<path>` 的 commit:path 计算 git blob 内容的 sha256。"""
        if commit_path in self._blob_cache:
            return self._blob_cache[commit_path] or None
        header, content = self._query(commit_path)
        if content is None or " blob " not in header:
            self._blob_cache[commit_path] = ""
            return None
        digest = hashlib.sha256(content).hexdigest()
        self._blob_cache[commit_path] = digest
        return digest

    def is_commit(self, commit: str) -> bool:
        """校验完整 40 位 commit SHA 的对象类型必须是 commit（拒绝可变引用）。"""
        if commit in self._commit_cache:
            return self._commit_cache[commit]
        header, content = self._query(commit)
        ok = content is not None and " commit " in header
        self._commit_cache[commit] = ok
        return ok


_GIT_BATCH: _GitCatFileBatch | None = None


def _git_batch() -> _GitCatFileBatch:
    """获取进程级批处理单例（懒加载，首次使用时才启动子进程）。"""
    global _GIT_BATCH
    if _GIT_BATCH is None:
        _GIT_BATCH = _GitCatFileBatch()
    return _GIT_BATCH


def _close_git_batch() -> None:
    """关闭批处理单例，保证下次检查重新启动干净进程（测试可统计启动次数）。"""
    global _GIT_BATCH
    if _GIT_BATCH is not None:
        _GIT_BATCH.close()
        _GIT_BATCH = None


def _git_blob_sha256(commit_path: str) -> str | None:
    """按 `git:<commit>:<path>` 的 commit:path 计算 git blob 内容的 sha256（批处理）。"""
    if commit_path in _GIT_BLOB_CACHE:
        return _GIT_BLOB_CACHE[commit_path] or None
    digest = _git_batch().blob_sha256(commit_path)
    _GIT_BLOB_CACHE[commit_path] = digest or ""
    return digest


def _is_commit_sha(commit: str) -> bool:
    """git: 工件引用只接受完整 40 位 commit SHA，且对象类型必须是 commit。

    拒绝 `HEAD` / 分支名 / 短 SHA 等可变引用，保证不可变绑定。
    """
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        return False
    if commit in _COMMIT_CACHE:
        return _COMMIT_CACHE[commit]
    ok = _git_batch().is_commit(commit)
    _COMMIT_CACHE[commit] = ok
    return ok


def _collect_file_integrity(
    entries: tuple[EvidenceEntry, ...], base_dir: Path
) -> tuple[tuple[dict[str, str | bool], ...], list[str]]:
    integrity: list[dict[str, str | bool]] = []
    issues: list[str] = []
    seen_paths: set[Path] = set()
    for entry in entries:
        if entry.fields.get("evidence_status", "active") == "retired":
            continue
        recorded_sha = entry.fields.get("sha256", "")
        sha_map = _parse_sha256_map(recorded_sha)
        file_like_refs = {
            _parse_reference(ref)[1]
            for ref in FILE_REFERENCE_RE.findall(entry.fields.get("file", ""))
            if _parse_reference(ref)[0] in ("repo", "local", "git")
        }
        for reference in FILE_REFERENCE_RE.findall(entry.fields.get("file", "")):
            scope, rel = _parse_reference(reference)
            if scope == "git":
                commit, sep, git_path = rel.partition(":")
                if not sep or not commit or not git_path:
                    issues.append(f"{entry.entry_id}: git 引用格式错误 `{reference}`")
                    continue
                if not _is_commit_sha(commit):
                    issues.append(
                        f"{entry.entry_id}: git 工件引用必须使用完整 40 位 commit SHA"
                        f"（拒绝 HEAD/分支名/短 SHA）：`{reference}`"
                    )
                    continue
                entry_commit = entry.fields.get("commit_sha", "")
                commit_map = _parse_commit_map(entry.fields.get("commit_map", ""))
                if entry_commit and commit != entry_commit:
                    if commit_map.get(git_path) != commit:
                        issues.append(
                            f"{entry.entry_id}: git 工件提交 {commit[:12]}.. 与条目 "
                            f"commit_sha {entry_commit[:12]}.. 不一致"
                            f"（跨提交工件须在 commit_map 声明 `{git_path}={commit}`）"
                        )
                commit_path = f"{commit}:{git_path}"
                digest = _git_blob_sha256(commit_path)
                if digest is None:
                    issues.append(f"{entry.entry_id}: git 工件缺失 `{reference}`")
                    integrity.append(
                        {
                            "path": commit_path,
                            "exists": False,
                            "sha256": "",
                            "kind": "git-blob-missing",
                        }
                    )
                    continue
                base_name = Path(git_path).name
                if re.fullmatch(r"[0-9a-f]{64}", recorded_sha):
                    expected = recorded_sha if digest == recorded_sha else None
                else:
                    expected = (
                        sha_map.get(git_path)
                        or sha_map.get(reference.strip().replace("\\", "/"))
                        or sha_map.get(base_name)
                    )
                if expected is None:
                    issues.append(
                        f"{entry.entry_id}: git 工件缺少 sha256 `{reference}`"
                    )
                elif expected != digest:
                    issues.append(
                        f"{entry.entry_id}: sha256 mismatch for `{reference}` "
                        f"(recorded {expected[:12]}.., actual {digest[:12]}..)"
                    )
                integrity.append(
                    {
                        "path": commit_path,
                        "exists": True,
                        "sha256": digest,
                        "kind": "git-blob",
                    }
                )
                continue
            if scope in ("production", "external", "url"):
                continue
            if scope not in ("repo", "local"):
                continue
            resolved_rel = LEGACY_FILE_ALIASES.get(rel, rel)
            resolved_path = (base_dir / resolved_rel).resolve() if rel else None
            if resolved_path is None or resolved_path in seen_paths:
                continue
            seen_paths.add(resolved_path)
            if not resolved_path.exists():
                if scope == "local":
                    integrity.append(
                        {
                            "path": str(resolved_path),
                            "exists": False,
                            "sha256": "",
                            "kind": "local-artifact-missing",
                        }
                    )
                    continue
                issues.append(f"{entry.entry_id}: repo 工件缺失 `{reference}`")
                integrity.append(
                    {
                        "path": str(resolved_path),
                        "exists": False,
                        "sha256": "",
                        "kind": "missing",
                    }
                )
                continue
            if resolved_path.is_dir():
                integrity.append(
                    {
                        "path": str(resolved_path),
                        "exists": True,
                        "sha256": "",
                        "kind": "directory",
                    }
                )
                continue
            digest = hashlib.sha256(resolved_path.read_bytes()).hexdigest()
            base_name = Path(rel).name
            if re.fullmatch(r"[0-9a-f]{64}", recorded_sha):
                if digest == recorded_sha:
                    expected = recorded_sha
                elif len(file_like_refs) == 1:
                    expected = recorded_sha
                else:
                    expected = None
            else:
                expected = (
                    sha_map.get(rel)
                    or sha_map.get(reference.strip().replace("\\", "/"))
                    or sha_map.get(base_name)
                )
            if rel == "docs/harness-engineering/core/evidence-index.md":
                integrity.append(
                    {
                        "path": str(resolved_path),
                        "exists": True,
                        "sha256": digest,
                        "kind": "registry",
                    }
                )
                continue
            if scope == "repo":
                if expected is None:
                    issues.append(
                        f"{entry.entry_id}: repo 工件缺少 sha256 `{reference}`"
                    )
                elif expected != digest:
                    issues.append(
                        f"{entry.entry_id}: sha256 mismatch for `{reference}` "
                        f"(recorded {expected[:12]}.., actual {digest[:12]}..)"
                    )
            integrity.append(
                {
                    "path": str(resolved_path),
                    "exists": True,
                    "sha256": digest,
                    "kind": "file",
                }
            )
    return tuple(integrity), issues


def check_evidence_index(path: Path = DEFAULT_EVIDENCE_INDEX) -> EvidenceCheckResult:
    if not path.exists():
        return EvidenceCheckResult(False, (), (f"evidence index not found: {path}",))
    content = path.read_text(encoding="utf-8-sig")
    entries = parse_entries(content)
    if not entries:
        return EvidenceCheckResult(False, (), ("evidence index has no entries",))
    base_dir = (
        ROOT_DIR if path.resolve() == DEFAULT_EVIDENCE_INDEX.resolve() else path.parent
    )
    try:
        file_integrity, file_issues = _collect_file_integrity(entries, base_dir)
        issues = validate_entries(entries)
        issues.extend(file_issues)
        return EvidenceCheckResult(not issues, entries, tuple(issues), file_integrity)
    finally:
        # 批处理子进程用完即关，避免句柄泄漏并保证测试可统计进程启动次数
        _close_git_batch()


def build_json_report(result: EvidenceCheckResult, path: Path) -> dict[str, object]:
    verified_files = sum(
        1
        for item in result.file_integrity
        if item.get("exists") is True and item.get("kind") == "file"
    )
    return {
        "status": "passed" if result.passed else "failed",
        "path": str(path),
        "total": len(result.entries),
        "retired": sum(
            1
            for entry in result.entries
            if entry.fields.get("evidence_status", "active") == "retired"
        ),
        "failed": len(result.issues),
        "issues": list(result.issues),
        "verified_files": verified_files,
        "file_integrity": list(result.file_integrity),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查 Harness evidence index 结构")
    parser.add_argument("--path", default=str(DEFAULT_EVIDENCE_INDEX), help="索引路径")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    index_path = Path(args.path)
    result = check_evidence_index(index_path)
    report = build_json_report(result, index_path)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if result.passed else 1
    if args.summary:
        print(
            "evidence_index "
            f"status={report['status']} total={report['total']} "
            f"retired={report['retired']} failed={report['failed']} "
            f"verified_files={report['verified_files']}"
        )
        return 0 if result.passed else 1
    if result.passed:
        print(f"[evidence-index] ok entries={len(result.entries)}")
        return 0
    print("[evidence-index] failed")
    for issue in result.issues:
        print(f"  - {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
