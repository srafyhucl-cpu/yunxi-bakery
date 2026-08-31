"""检查项目完整开发总表与任务指令的一致性。

脚本只读解析 PROJECT-STATE.md 和 docs/tasks/*.md，不修改文件、不生成缓存。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

ROOT_DIR = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT_DIR / "PROJECT-STATE.md"
VERSION_FILE = ROOT_DIR / "backend" / "VERSION"
TASKS_DIR = ROOT_DIR / "docs" / "tasks"
MACHINE_BLOCK_RE = re.compile(
    r"<!--\s*PROJECT_STATE_MACHINE_START\s*-->(.*?)<!--\s*PROJECT_STATE_MACHINE_END\s*-->",
    re.DOTALL | re.IGNORECASE,
)
YAML_FIELD_RE = re.compile(r"^([a-z_]+):\s*(.*?)\s*$", re.MULTILINE)
TASK_FIELD_RE = re.compile(r"^(?:>\s*)?([a-z_]+):\s*(.*?)\s*$", re.MULTILINE)
SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ASCII_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]*$")
ALLOWED_STATUSES = frozenset(
    {"completed", "active", "blocked", "pending", "deferred", "historical"}
)
STATUS_LABELS = {
    "completed": "已完成（completed）",
    "active": "进行中（active）",
    "blocked": "已阻塞（blocked）",
    "pending": "待处理（pending）",
    "deferred": "已暂缓（deferred）",
    "historical": "历史（historical）",
}
REQUIRED_SNAPSHOT_FIELDS = (
    "updated_at",
    "as_of_commit",
    "version",
    "current_branch",
    "workspace_state",
    "state_owner",
)
REQUIRED_TASK_COLUMNS = (
    "task_id",
    "status",
    "状态说明",
    "owner",
    "branch",
    "as_of_commit",
    "依赖",
    "证据",
    "下一步",
)
REQUIRED_BRANCH_COLUMNS = ("branch_or_track", "类型", "状态", "基线", "绑定任务")
VIEW_HEADINGS = {
    "completed": "已完成（completed）",
    "active": "进行中（active）",
    "unfinished": "未完成（pending / blocked / deferred）",
    "historical": "历史（historical）",
}
VIEW_ALLOWED_STATUSES = {
    "completed": {"completed"},
    "active": {"active"},
    "unfinished": {"pending", "blocked", "deferred"},
    "historical": {"historical"},
}


@dataclass(frozen=True)
class RegisterResult:
    """总表检查结果。"""

    passed: bool
    issues: tuple[str, ...]
    task_statuses: dict[str, str]
    task_branches: dict[str, str] = field(default_factory=dict)


def _validate_human_status_display(content: str, issues: list[str]) -> None:
    """禁止 PROJECT-STATE 中文叙述中裸写机器状态码。"""
    human_content = MACHINE_BLOCK_RE.sub("", content)
    in_fence = False
    for line_number, line in enumerate(human_content.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or re.match(r"^\s*>?\s*status(?:_label)?\s*:", line):
            continue
        for status in STATUS_LABELS:
            if re.search(rf"(?i)(?<![\w（(]){re.escape(status)}(?![\w）)])", line):
                issues.append(
                    "PROJECT-STATE 中文状态展示缺少中文标签: "
                    f"第 {line_number} 行应使用 {STATUS_LABELS[status]}"
                )
                break


def _split_table(block: str, heading: str) -> tuple[list[str], list[list[str]]]:
    """读取指定标题后的第一个 Markdown 表格。"""
    heading_pos = block.find(heading)
    if heading_pos < 0:
        return [], []
    lines = block[heading_pos:].splitlines()[1:]
    table_lines: list[str] = []
    for line in lines:
        if line.startswith("|"):
            table_lines.append(line)
        elif table_lines:
            break
    if len(table_lines) < 2:
        return [], []
    headers = [
        cell.strip().strip(chr(96))
        for cell in table_lines[0].strip().strip("|").split("|")
    ]
    rows: list[list[str]] = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(cells)
    return headers, rows


def _extract_inline_ids(text: str) -> list[str]:
    """从状态视图文本中提取任务标识。"""
    return re.findall(r"\x60([A-Z0-9][A-Z0-9_-]*)\x60", text)


def _git(*args: str) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return False, str(exc)
    output = completed.stdout.strip() or completed.stderr.strip()
    return completed.returncode == 0, output


def _read_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def _display_path(path: Path) -> str:
    """返回可读路径；临时目录不在仓库内时保留绝对路径。"""
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def _validate_commit(commit: str, label: str, issues: list[str]) -> None:
    if not commit:
        return
    if not SHA_RE.fullmatch(commit):
        issues.append(f"{label}: as_of_commit 格式无效 {commit}")
        return
    resolved, _ = _git("rev-parse", "--verify", f"{commit}^{{commit}}")
    if not resolved:
        # 外部冻结轨道的历史提交不在当前仓库对象库中，改到对应仓库只读核验。
        if label.startswith("T-D1-") or "YunxiBakeBot" in label:
            legacy_root = Path(r"D:\Project\YunxiBakeBot")
            if legacy_root.exists():
                try:
                    legacy = subprocess.run(
                        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
                        cwd=legacy_root,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                    )
                except OSError:
                    legacy = None
                if legacy is not None and legacy.returncode == 0:
                    return
        issues.append(f"{label}: as_of_commit 无法解析 {commit}")


def _validate_snapshot_freshness(commit: str, issues: list[str]) -> None:
    """机器快照只能引用当前代码或本次状态提交前的代码快照。"""
    if not commit:
        return
    snapshot_ok, resolved_snapshot = _git(
        "rev-parse", "--verify", f"{commit}^{{commit}}"
    )
    if not snapshot_ok or not SHA_RE.fullmatch(resolved_snapshot):
        return
    head_ok, head = _git("rev-parse", "HEAD")
    if not head_ok or not SHA_RE.fullmatch(head):
        issues.append("无法读取当前 HEAD，无法校验机器快照新鲜度")
        return
    allowed_commits = {head}
    parent_ok, parent = _git("rev-parse", "HEAD^")
    if parent_ok and SHA_RE.fullmatch(parent):
        allowed_commits.add(parent)
    if resolved_snapshot not in allowed_commits:
        issues.append(f"机器快照 as_of_commit 已过期: 文档={commit}，当前 HEAD={head}")


def parse_register(path: Path = STATE_FILE) -> RegisterResult:
    """解析并校验项目状态总表。"""
    issues: list[str] = []
    if not path.exists():
        return RegisterResult(False, (f"缺少项目状态文件: {path}",), {})
    try:
        content = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return RegisterResult(False, (f"无法读取项目状态文件: {exc}",), {})
    _validate_human_status_display(content, issues)
    match = MACHINE_BLOCK_RE.search(content)
    if not match:
        return RegisterResult(
            False, ("PROJECT_STATE_MACHINE 区块不存在或标记不完整",), {}
        )
    block = match.group(1)
    fence = chr(96) * 3
    snapshot_match = re.search(
        fence + r"yaml\s*(.*?)" + fence, block, re.DOTALL | re.IGNORECASE
    )
    snapshot = (
        {
            m.group(1): m.group(2).strip()
            for m in YAML_FIELD_RE.finditer(snapshot_match.group(1))
        }
        if snapshot_match
        else {}
    )
    for field_name in REQUIRED_SNAPSHOT_FIELDS:
        if not snapshot.get(field_name):
            issues.append(f"机器快照缺少字段 {field_name}")
    if snapshot.get("updated_at") and not DATE_RE.fullmatch(snapshot["updated_at"]):
        issues.append("机器快照 updated_at 必须是 YYYY-MM-DD")
    if snapshot.get("workspace_state") not in {"clean", "dirty"}:
        issues.append("机器快照 workspace_state 必须为 clean 或 dirty")

    task_headers, task_rows = _split_table(block, "## 主线任务总表")
    missing_columns = [
        column for column in REQUIRED_TASK_COLUMNS if column not in task_headers
    ]
    if missing_columns:
        issues.append(f"主线任务总表缺少列: {', '.join(missing_columns)}")
    tasks: dict[str, dict[str, str]] = {}
    for row_number, row in enumerate(task_rows, start=1):
        record = dict(zip(task_headers, row))
        task_id = record.get("task_id", "").strip()
        if not task_id:
            issues.append(f"主线任务总表第 {row_number} 行缺少 task_id")
            continue
        if task_id in tasks:
            issues.append(f"task_id 重复: {task_id}")
        if not ASCII_ID_RE.fullmatch(task_id):
            issues.append(f"task_id 非稳定 ASCII 标识: {task_id}")
        status = record.get("status", "").strip()
        if status not in ALLOWED_STATUSES:
            issues.append(f"{task_id}: 非法 status {status}")
        status_label = record.get("状态说明", "").strip()
        expected_label = STATUS_LABELS.get(status)
        if not status_label:
            issues.append(f"{task_id}: 缺少状态说明")
        elif expected_label and status_label != expected_label:
            issues.append(
                f"{task_id}: 状态说明与 status 不一致: "
                f"应为 {expected_label}，实际为 {status_label}"
            )
        for column in REQUIRED_TASK_COLUMNS:
            if not record.get(column, "").strip():
                issues.append(f"{task_id}: 缺少字段 {column}")
        _validate_commit(record.get("as_of_commit", "").strip(), task_id, issues)
        tasks[task_id] = record

    view_ids: dict[str, list[str]] = {}
    for view_name, heading in VIEW_HEADINGS.items():
        heading_pos = block.find(f"### {heading}")
        if heading_pos < 0:
            issues.append(f"缺少状态视图: {heading}")
            continue
        next_heading = block.find("### ", heading_pos + 4)
        view_text = block[
            heading_pos : next_heading if next_heading >= 0 else len(block)
        ]
        ids = _extract_inline_ids(view_text)
        view_ids[view_name] = ids
        for task_id in ids:
            if task_id not in tasks:
                issues.append(f"状态视图引用不存在的 task_id: {task_id}")
    for view_name, ids in view_ids.items():
        for task_id in ids:
            if task_id not in tasks:
                continue
            actual = tasks[task_id]["status"]
            if actual not in VIEW_ALLOWED_STATUSES[view_name]:
                issues.append(
                    f"状态视图 {view_name} 与 {task_id} 的 status 冲突: {actual}"
                )
    all_view_ids = {task_id for ids in view_ids.values() for task_id in ids}
    for task_id in tasks:
        if task_id not in all_view_ids:
            issues.append(f"主线任务未出现在任何状态视图: {task_id}")

    branch_headers, branch_rows = _split_table(block, "## 分支与开发轨道登记")
    for column in REQUIRED_BRANCH_COLUMNS:
        if column not in branch_headers:
            issues.append(f"分支登记表缺少列: {column}")
    branch_names = {row[0].strip() for row in branch_rows if row}
    branch_ok, actual_branch = _git("branch", "--show-current")
    if not branch_ok or not actual_branch:
        issues.append("无法读取当前 Git 分支")
    if (
        snapshot.get("current_branch")
        and actual_branch
        and snapshot["current_branch"] != actual_branch
    ):
        issues.append(
            f"current_branch 与 Git 不一致: 文档={snapshot['current_branch']}，Git={actual_branch}"
        )
    status_ok, porcelain = _git("status", "--porcelain")
    if status_ok and snapshot.get("workspace_state"):
        actual_workspace_state = "dirty" if porcelain else "clean"
        if snapshot["workspace_state"] != actual_workspace_state:
            issues.append(
                "workspace_state 与 Git 不一致: "
                f"文档={snapshot['workspace_state']}，Git={actual_workspace_state}"
            )
    if actual_branch and actual_branch not in branch_names:
        issues.append(f"分支登记表未登记当前 Git 分支: {actual_branch}")
    local_ok, local_branches = _git(
        "for-each-ref", "--format=%(refname:short)", "refs/heads"
    )
    if local_ok:
        real_local = set(filter(None, local_branches.splitlines()))
        for branch_name in branch_names:
            if branch_name.startswith("external:") or ":\\" in branch_name:
                continue
            if branch_name not in real_local:
                issues.append(f"分支登记表包含不存在的本地分支: {branch_name}")

    version = _read_version()
    if snapshot.get("version") != version:
        issues.append(
            f"状态版本与 backend/VERSION 不一致: 文档={snapshot.get('version', '')}，文件={version}"
        )
    snapshot_commit = snapshot.get("as_of_commit", "")
    _validate_commit(snapshot_commit, "机器快照", issues)
    _validate_snapshot_freshness(snapshot_commit, issues)
    task_statuses = {
        task_id: record.get("status", "") for task_id, record in tasks.items()
    }
    task_branches = {
        task_id: record.get("branch", "") for task_id, record in tasks.items()
    }
    return RegisterResult(not issues, tuple(issues), task_statuses, task_branches)


def parse_task_metadata(path: Path) -> tuple[dict[str, str], list[str]]:
    """读取任务指令头部元数据并返回问题。"""
    required = (
        "task_id",
        "owner",
        "status",
        "status_label",
        "as_of_commit",
        "version",
        "branch",
        "allowed_paths",
        "forbidden_paths",
    )
    try:
        content = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return {}, [f"{path}: 无法读取任务指令: {exc}"]
    # 只解析标题后的连续元数据区，避免正文中的历史快照覆盖当前字段。
    lines = content.splitlines()
    title_index = next(
        (index for index, line in enumerate(lines) if line.lstrip().startswith("#")),
        -1,
    )
    metadata: dict[str, str] = {}
    started = False
    if title_index >= 0:
        for line in lines[title_index + 1 :]:
            if not line.strip() and not started:
                continue
            match = TASK_FIELD_RE.fullmatch(line)
            if match is None:
                if started:
                    break
                continue
            started = True
            if match.group(1) in required:
                metadata[match.group(1)] = match.group(2).strip()
    issues: list[str] = []
    rel = _display_path(path)
    for field_name in required:
        if not metadata.get(field_name):
            issues.append(f"{rel}: 缺少元数据 {field_name}")
    task_id = metadata.get("task_id", "")
    if task_id and not ASCII_ID_RE.fullmatch(task_id):
        issues.append(f"{rel}: task_id 非法 {task_id}")
    status = metadata.get("status", "")
    if status and status not in ALLOWED_STATUSES:
        issues.append(f"{rel}: 非法 status {status}")
    status_label = metadata.get("status_label", "")
    expected_label = STATUS_LABELS.get(status)
    if not status_label:
        issues.append(f"{rel}: 缺少元数据 status_label")
    elif expected_label and status_label != expected_label:
        issues.append(
            f"{rel}: status_label 与 status 不一致: "
            f"应为 {expected_label}，实际为 {status_label}"
        )
    _validate_commit(metadata.get("as_of_commit", ""), rel, issues)
    version = _read_version()
    if metadata.get("version") and metadata["version"] != version:
        issues.append(f"{rel}: version 与 backend/VERSION 不一致")
    return metadata, issues


def check_project_development_register(
    state_path: Path = STATE_FILE, tasks_dir: Path = TASKS_DIR
) -> RegisterResult:
    """检查总表和全部任务指令。"""
    register = parse_register(state_path)
    issues = list(register.issues)
    seen_task_docs: dict[str, Path] = {}
    if not tasks_dir.exists():
        issues.append(f"缺少任务指令目录: {tasks_dir}")
    else:
        for task_path in sorted(tasks_dir.glob("*.md")):
            metadata, metadata_issues = parse_task_metadata(task_path)
            issues.extend(metadata_issues)
            task_id = metadata.get("task_id", "")
            if not task_id:
                continue
            if task_id in seen_task_docs:
                issues.append(f"任务指令 task_id 重复: {task_id}")
            seen_task_docs[task_id] = task_path
            if task_id not in register.task_statuses:
                issues.append(f"任务指令 {task_id} 未登记在 PROJECT-STATE.md")
            elif (
                metadata.get("status")
                and metadata["status"] != register.task_statuses[task_id]
            ):
                issues.append(
                    f"任务指令 {task_id} status 与总表不一致: 文档={metadata['status']}，总表={register.task_statuses[task_id]}"
                )
            register_branch = register.task_branches.get(task_id, "")
            if (
                metadata.get("branch")
                and register_branch
                and metadata["branch"] != register_branch
            ):
                issues.append(
                    f"任务指令 {task_id} branch 与总表不一致: "
                    f"文档={metadata['branch']}，总表={register_branch}"
                )
    return RegisterResult(not issues, tuple(issues), register.task_statuses)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查项目完整开发总表")
    parser.add_argument("--state", default=str(STATE_FILE), help="项目状态文件路径")
    parser.add_argument("--tasks-dir", default=str(TASKS_DIR), help="任务指令目录")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = check_project_development_register(Path(args.state), Path(args.tasks_dir))
    if result.passed:
        print(f"[开发总表] PASS tasks={len(result.task_statuses)}")
        return 0
    print("[开发总表] FAIL")
    for issue in result.issues:
        print(f"  - {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
