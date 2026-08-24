# -*- coding: utf-8 -*-
"""
Pre-commit hook: 检查本次暂存的变更是否同步更新了必要的项目文档。
当有 .py / .html / .css / .js 文件被暂存时，要求以下两份文档也在暂存区：
  1. LOGBOOK.md          — 开发日志（技术变更编年史）
  2. 项目进度与配置清单.md  — 项目进度与配置状态（进度/功能/已知问题等）
可用环境变量 SKIP_LOGBOOK_CHECK=1 临时跳过（纯配置/格式修正时使用）。
"""

import os
import subprocess
import sys

# 强制 stdout 使用 UTF-8，避免 Windows GBK 编码下 pre-commit 管道卡死
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SKIP_SENTINEL = "SKIP_LOGBOOK_CHECK"

REQUIRED_DOCS = [
    "LOGBOOK.md",
    "项目进度与配置清单.md",
]

CODE_EXTENSIONS = {".py", ".html", ".css", ".js"}


def get_staged_files() -> list[str]:
    # core.quotepath=false 禁止 git 对中文文件名做八进制转义
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


def main() -> int:
    if os.environ.get(SKIP_SENTINEL):
        print("[doc-check] 跳过检查（环境变量 SKIP_LOGBOOK_CHECK 已设置）")
        return 0

    staged = get_staged_files()
    if not staged:
        return 0

    has_code = any(any(f.endswith(ext) for ext in CODE_EXTENSIONS) for f in staged)
    if not has_code:
        return 0

    missing = [doc for doc in REQUIRED_DOCS if doc not in staged]
    if not missing:
        return 0

    print("\n[doc-check] 检测到代码文件变更，但以下文档未在暂存区：\n")
    for doc in missing:
        print(f"  [MISS] {doc}")

    print(
        "\n  请更新后 git add，格式参见 .windsurf/workflows/commit.md 第 4、5 步。"
        "\n"
        "\n  如确认本次变更无需记录（纯配置/格式修正），可临时跳过："
        "\n    SKIP_LOGBOOK_CHECK=1 git commit ..."
        "\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
