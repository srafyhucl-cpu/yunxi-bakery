# -*- coding: utf-8 -*-
"""
Pre-commit hook: 版本同步门禁。

在每次代码提交时自动执行三项检查与更新：
  1. 根据提交类型自动递增 VERSION 文件中的版本号
  2. 验证 VERSION 与 config.py 中的 APP_VERSION 保持一致
  3. 校验 LOGBOOK.md 和项目进度与配置清单.md 已同步更新

版本递增规则（基于 Conventional Commits）：
  - feat! / BREAKING CHANGE → 主版本号 (major)
  - feat / perf / refactor  → 次版本号 (minor)
  - fix / docs / style / chore / test → 修订号 (patch)

可用环境变量：
  SKIP_VERSION_BUMP=1   — 跳过版本递增与文档校验（紧急修复时使用）
  VERSION_BUMP=patch    — 强制指定递增类型（major/minor/patch）

用法（由 .pre-commit-config.yaml 自动调用）：
  python scripts/sync_version.py [commit_msg_file]
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# 强制 stdout 使用 UTF-8，避免 Windows GBK 编码下 pre-commit 管道卡死
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── 项目根目录 ──
ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
LOGBOOK_FILE = ROOT / "LOGBOOK.md"
PROGRESS_FILE = ROOT / "项目进度与配置清单.md"
CONFIG_FILE = ROOT / "app" / "config.py"

CODE_EXTENSIONS = {".py", ".html", ".css", ".js", ".ts", ".vue", ".sql"}

SKIP_ENV = "SKIP_VERSION_BUMP"
FORCE_BUMP_ENV = "VERSION_BUMP"


# ────────────────────────────────────────────
# 1. 版本号工具
# ────────────────────────────────────────────


def read_version() -> str:
    """读取 VERSION 文件中的当前版本号。"""
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def write_version(version: str) -> None:
    """写入新版本号到 VERSION 文件。"""
    VERSION_FILE.write_text(version + "\n", encoding="utf-8")


def bump_version(current: str, bump_type: str) -> str:
    """根据递增类型计算新版本号。"""
    parts = current.split(".")
    if len(parts) != 3:
        print(
            f"[version-sync] [WARN] VERSION 文件格式异常: {current!r}，预期 semver (x.y.z)"
        )
        return current

    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "patch":
        patch += 1
    else:
        print(f"[version-sync] [WARN] 未知递增类型: {bump_type!r}，跳过版本递增")
        return current

    return f"{major}.{minor}.{patch}"


def determine_bump_type(commit_msg: str) -> str:
    """
    根据提交信息判断版本递增类型。

    规则（基于 Conventional Commits）：
      - feat! / BREAKING CHANGE → major
      - feat / perf / refactor  → minor
      - 其余（fix/docs/style/chore/test等）→ patch
    """
    first_line = commit_msg.strip().splitlines()[0].strip()

    # 检查 breaking change
    if "BREAKING CHANGE" in commit_msg or first_line.startswith("feat!"):
        return "major"

    # 检查提交类型前缀
    match = re.match(r"^(\w+)(\([^)]*\))?!?:", first_line)
    if match:
        commit_type = match.group(1)
        if commit_type in ("feat", "perf", "refactor"):
            return "minor"

    return "patch"


def read_commit_msg_from_file(filepath: str) -> str:
    """从 commit-msg 文件中读取提交信息。"""
    try:
        return Path(filepath).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def get_staged_commit_msg() -> str:
    """
    尝试从暂存区或 git 环境获取即将提交的 commit message。
    如果获取不到，则返回空字符串（将默认递增 patch）。
    """
    # 优先使用传入的 commit-msg 文件路径
    if len(sys.argv) > 1:
        msg = read_commit_msg_from_file(sys.argv[1])
        if msg:
            return msg

    # 尝试从 .git/COMMIT_EDITMSG 读取
    commit_editmsg = ROOT / ".git" / "COMMIT_EDITMSG"
    if commit_editmsg.exists():
        try:
            return commit_editmsg.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            pass

    return ""


# ────────────────────────────────────────────
# 2. 文档同步校验
# ────────────────────────────────────────────


def get_staged_files() -> list[str]:
    """获取本次暂存的文件列表。"""
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.quotepath=false",
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMR",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip().splitlines()


def has_code_changes(staged: list[str]) -> bool:
    """判断暂存区中是否存在代码变更。"""
    return any(any(f.endswith(ext) for ext in CODE_EXTENSIONS) for f in staged)


def check_doc_sync(staged: list[str]) -> list[str]:
    """
    检查关键文档是否在暂存区中。
    返回缺失的文档列表。
    """
    required_docs = [LOGBOOK_FILE.name, PROGRESS_FILE.name]
    staged_names = set(staged)
    return [doc for doc in required_docs if doc not in staged_names]


def check_config_version_consistency(new_version: str) -> bool:
    """
    验证 config.py 中引用的 VERSION 文件能正确读取到新版本号。
    由于 config.py 在导入时读取 VERSION，这里只检查文件存在性。
    """
    if not VERSION_FILE.exists():
        print(f"[version-sync] [ERR] VERSION 文件不存在: {VERSION_FILE}")
        return False

    actual = read_version()
    if actual != new_version:
        print(
            f"[version-sync] [ERR] VERSION 文件内容不一致: 期望 {new_version!r}，实际 {actual!r}"
        )
        return False

    return True


# ────────────────────────────────────────────
# 3. 版本号注入到项目进度与配置清单
# ────────────────────────────────────────────


def inject_version_to_progress(new_version: str) -> bool:
    """在项目进度与配置清单.md 的表头中注入版本号。"""
    if not PROGRESS_FILE.exists():
        print(f"[version-sync] [ERR] 项目进度文件不存在: {PROGRESS_FILE}")
        return False

    content = PROGRESS_FILE.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")

    current_pattern = (
        r"(?m)^> 最后更新\s+\d{4}-\d{2}-\d{2}\s+-\s+"
        r"当前本地代码版本为\s+`\d+\.\d+\.\d+`。"
    )
    current_replacement = f"> 最后更新 {today} - 当前本地代码版本为 `{new_version}`。"
    new_content, count = re.subn(
        current_pattern,
        current_replacement,
        content,
        count=1,
    )

    if count == 0:
        legacy_pattern = (
            r"> 最后更新:\s*\d{4}-\d{2}-\d{2}（[^）]+）—\s*"
            r"v?\d+\.\d+\.\d+\s*"
        )
        legacy_replacement = f"> 最后更新: {today}（自动版本同步）— v{new_version} "
        new_content, count = re.subn(
            legacy_pattern,
            legacy_replacement,
            content,
            count=1,
        )

    if count == 0:
        # 如果没有匹配到版本号标记，尝试在"最后更新"行后追加版本号
        pattern2 = r"(> 最后更新:\s*\d{4}-\d{2}-\d{2}（[^）]+）—\s*)"
        new_content, count = re.subn(
            pattern2,
            f"\\1v{new_version} ",
            content,
            count=1,
        )

    if count == 0:
        print("[version-sync] [ERR] 项目进度表头格式无法识别，版本号未同步")
        return False

    if new_content != content:
        PROGRESS_FILE.write_text(new_content, encoding="utf-8")
    print(f"[version-sync] [OK] 已将 v{new_version} 注入到项目进度与配置清单.md")
    return True


def stage_generated_file(path: Path, label: str) -> bool:
    """暂存版本同步生成的文件。"""
    result = subprocess.run(
        ["git", "add", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode == 0:
        print(f"[version-sync] [OK] {label} 已加入暂存区")
        return True
    print(f"[version-sync] [ERR] git add {label} 失败: {result.stderr.strip()}")
    return False


# ────────────────────────────────────────────
# 4. 主流程
# ────────────────────────────────────────────


def main() -> int:
    # 0. 检查跳过标志
    if os.environ.get(SKIP_ENV):
        print(f"[version-sync] 跳过检查（环境变量 {SKIP_ENV} 已设置）")
        return 0

    staged = get_staged_files()
    if not staged:
        return 0

    # 1. 判断是否有代码变更
    if not has_code_changes(staged):
        print("[version-sync] 非代码变更，跳过版本递增")
        return 0

    # 2. 读取当前版本号
    current_version = read_version()
    print(f"[version-sync] 当前版本: v{current_version}")

    # 3. 确定递增类型
    force_bump = os.environ.get(FORCE_BUMP_ENV)
    if force_bump in ("major", "minor", "patch"):
        bump_type = force_bump
        print(
            f"[version-sync] 强制递增类型: {bump_type}（来自环境变量 {FORCE_BUMP_ENV}）"
        )
    else:
        commit_msg = get_staged_commit_msg()
        bump_type = determine_bump_type(commit_msg)
        print(f"[version-sync] 递增类型: {bump_type}（基于提交信息推断）")

    # 4. 计算并写入新版本号
    new_version = bump_version(current_version, bump_type)
    if new_version == current_version:
        print("[version-sync] 版本号未变化，跳过后续步骤")
        return 0

    write_version(new_version)
    print(f"[version-sync] [OK] VERSION 已更新: v{current_version} -> v{new_version}")

    # 5. 注入版本号到项目进度与配置清单
    if not inject_version_to_progress(new_version):
        write_version(current_version)
        print(f"[version-sync] 已回滚 VERSION 到 v{current_version}")
        return 1

    # 6. 自动暂存两个版本来源文件
    if not stage_generated_file(VERSION_FILE, "VERSION"):
        write_version(current_version)
        print(f"[version-sync] 已回滚 VERSION 到 v{current_version}")
        return 1
    if not stage_generated_file(PROGRESS_FILE, "项目进度与配置清单.md"):
        return 1

    # 7. 校验文档同步
    missing_docs = check_doc_sync(staged + [VERSION_FILE.name])
    if missing_docs:
        print("\n[version-sync] [WARN] 以下文档未在暂存区（建议同步更新）：\n")
        for doc in missing_docs:
            print(f"  [MISS] {doc}")
        print(
            "\n  提示: 如果本次变更已更新过这些文档，请 git add 后重新提交。"
            "\n  如确认无需更新，可临时跳过: SKIP_VERSION_BUMP=1 git commit ...\n"
        )
        # 文档缺失仅警告，不阻断提交（由 check_logbook.py 负责阻断）
    else:
        print("[version-sync] [OK] 文档同步检查通过")

    # 8. 最终一致性校验
    if not check_config_version_consistency(new_version):
        write_version(current_version)
        print(f"[version-sync] 一致性校验失败，已回滚 VERSION 到 v{current_version}")
        return 1

    print(f"\n[version-sync] [OK] 版本同步完成: v{current_version} -> v{new_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
