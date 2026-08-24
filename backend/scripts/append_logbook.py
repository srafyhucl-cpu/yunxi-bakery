# -*- coding: utf-8 -*-
"""
LOGBOOK 自动追加工具。

根据传入的变更信息，自动在 LOGBOOK.md 顶部追加一条格式化的开发日志条目，
同时自动读取 VERSION 文件获取当前版本号。

用法：
  # 交互模式（推荐）
  python scripts/append_logbook.py

  # 命令行参数模式
  python scripts/append_logbook.py --type feat --scope product --desc "新增商品批量导入功能"

  # 完整模式（含关联任务和文件列表）
  python scripts/append_logbook.py --type fix --scope chat --desc "修复并发场景会话竞争" --task "用户反馈偶发回复错乱" --files "app/service/chat.py,app/service/session_manager.py"

支持的变更类型（Conventional Commits）：
  feat      新功能
  fix       Bug 修复
  refactor  重构
  perf      性能优化
  style     样式调整
  docs      文档
  chore     构建/工程
  test      测试
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGBOOK_FILE = ROOT / "LOGBOOK.md"
VERSION_FILE = ROOT / "VERSION"

# 变更类型映射
TYPE_LABELS = {
    "feat": "feat",
    "fix": "fix",
    "refactor": "refactor",
    "perf": "perf",
    "style": "style",
    "docs": "docs",
    "chore": "chore",
    "test": "test",
}


def read_version() -> str:
    """读取当前版本号。"""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    return "0.0.0"


def get_today() -> str:
    """获取今天的日期字符串。"""
    return datetime.now().strftime("%Y-%m-%d")


def get_git_diff_files() -> list[str]:
    """获取当前暂存区中变更的文件列表。"""
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


def build_logbook_entry(
    change_type: str,
    scope: str,
    desc: str,
    task: str = "",
    files: list[str] | None = None,
    operator: str = "AI (CodeBuddy)",
) -> str:
    """
    构建一条 LOGBOOK 条目。

    格式：
    ## [YYYY-MM-DD] - type(scope): 描述

    - **操作人**: operator
    - **关联任务**: task
    - **改动**:
      - file1: 改动说明
      - file2: 改动说明
    - **版本**: vX.Y.Z
    """
    today = get_today()
    version = read_version()

    # 构建标题行
    scope_part = f"({scope})" if scope else ""
    title = f"## [{today}] - {change_type}{scope_part}: {desc}"

    # 构建条目
    lines = [title, ""]

    lines.append(f"- **操作人**: {operator}")

    if task:
        lines.append(f"- **关联任务**: {task}")

    lines.append("- **改动**:")
    if files:
        for f in files:
            lines.append(f"  - `{f}`")
    else:
        lines.append(f"  - {desc}")

    lines.append(f"- **版本**: v{version}")
    lines.append("")

    return "\n".join(lines)


def prepend_to_logbook(entry: str) -> None:
    """将条目追加到 LOGBOOK.md 的顶部（标题之后）。"""
    if not LOGBOOK_FILE.exists():
        print(f"[logbook] ❌ LOGBOOK.md 不存在: {LOGBOOK_FILE}")
        sys.exit(1)

    content = LOGBOOK_FILE.read_text(encoding="utf-8")

    # 找到第一个 ## 标题的位置，在其前面插入
    match = re.search(r"^##\s", content, re.MULTILINE)
    if match:
        insert_pos = match.start()
        new_content = content[:insert_pos] + entry + "\n" + content[insert_pos:]
    else:
        # 如果没有找到 ## 标题，追加到文件末尾
        new_content = content.rstrip() + "\n\n" + entry

    LOGBOOK_FILE.write_text(new_content, encoding="utf-8")


def interactive_mode() -> tuple[str, str, str, str, list[str]]:
    """交互式输入模式。"""
    print("\n📝 LOGBOOK 条目生成器")
    print("=" * 40)

    # 变更类型
    print("\n变更类型:")
    for i, (key, _) in enumerate(TYPE_LABELS.items(), 1):
        print(f"  {i}. {key}")
    type_choice = input("请选择 (1-8) [默认 patch=2]: ").strip()
    type_map = list(TYPE_LABELS.keys())
    try:
        change_type = type_map[int(type_choice) - 1] if type_choice else "fix"
    except (ValueError, IndexError):
        change_type = "fix"

    # 范围
    scope = input("范围 (如 chat/product/webhook，可留空): ").strip()

    # 描述
    desc = input("变更描述 (必填): ").strip()
    if not desc:
        print("[logbook] ❌ 变更描述不能为空")
        sys.exit(1)

    # 关联任务
    task = input("关联任务 (可留空): ").strip()

    # 文件列表（自动检测暂存区）
    staged = get_git_diff_files()
    if staged:
        print(f"\n暂存区文件 ({len(staged)} 个):")
        for f in staged:
            print(f"  - {f}")
        use_staged = input("是否自动关联暂存区文件？(Y/n): ").strip().lower()
        files = staged if use_staged != "n" else []
    else:
        files = []

    return change_type, scope, desc, task, files


def main() -> int:
    parser = argparse.ArgumentParser(description="LOGBOOK 自动追加工具")
    parser.add_argument("--type", "-t", choices=TYPE_LABELS.keys(), help="变更类型")
    parser.add_argument("--scope", "-s", default="", help="变更范围")
    parser.add_argument("--desc", "-d", default="", help="变更描述")
    parser.add_argument("--task", default="", help="关联任务")
    parser.add_argument("--files", "-f", default="", help="变更文件列表（逗号分隔）")
    parser.add_argument("--operator", default="AI (CodeBuddy)", help="操作人")

    args = parser.parse_args()

    if args.type and args.desc:
        # 命令行模式
        change_type = args.type
        scope = args.scope
        desc = args.desc
        task = args.task
        files = (
            [f.strip() for f in args.files.split(",") if f.strip()]
            if args.files
            else []
        )
        operator = args.operator
    else:
        # 交互模式
        change_type, scope, desc, task, files = interactive_mode()
        operator = "AI (CodeBuddy)"

    # 构建并写入条目
    entry = build_logbook_entry(
        change_type=change_type,
        scope=scope,
        desc=desc,
        task=task,
        files=files,
        operator=operator,
    )

    prepend_to_logbook(entry)

    version = read_version()
    print("\n[logbook] ✅ 条目已追加到 LOGBOOK.md")
    print(f"[logbook]    类型: {change_type} | 范围: {scope or '-'} | 版本: v{version}")
    print(f"[logbook]    描述: {desc}")
    print()
    print("  下一步: git add LOGBOOK.md 项目进度与配置清单.md && git commit")

    return 0


if __name__ == "__main__":
    sys.exit(main())
