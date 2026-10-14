"""检查仓库中文文本是否出现明显乱码或替换字符。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = (
    "AGENTS.md",
    "README.md",
    "LOGBOOK.md",
    "项目进度与配置清单.md",
    "docs",
    ".agents/skills",
)
TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".py",
    ".ps1",
    ".yaml",
    ".yml",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".vue",
}
MOJIBAKE_MARKERS = (
    "\u947a",
    "\u9414",
    "\u7039",
    "\u9357",
    "\u6d93",
    "\u93b4",
    "\u7ec2",
    "\u9286",
    "\u9225",
    "\u9983",
)


def _iter_text_files(targets: list[Path]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        if target.is_file() and target.suffix.lower() in TEXT_SUFFIXES:
            files.append(target)
        elif target.is_dir():
            files.extend(
                path
                for path in target.rglob("*")
                if path.is_file()
                and path.suffix.lower() in TEXT_SUFFIXES
                and ".git" not in path.parts
                and "node_modules" not in path.parts
                and ".venv" not in path.parts
            )
    return sorted(set(files))


def _scan_file(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        return [f"无法按 UTF-8 解码: {exc}"]

    if "\ufffd" in text:
        issues.append("包含 Unicode replacement character U+FFFD")

    marker_hits = sorted({marker for marker in MOJIBAKE_MARKERS if marker in text})
    if marker_hits:
        issues.append(f"疑似 UTF-8/GBK mojibake 标记: {', '.join(marker_hits)}")

    return issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查中文文本文件是否存在明显乱码")
    parser.add_argument(
        "paths",
        nargs="*",
        help="可选扫描路径；默认扫描 AGENTS、README、LOGBOOK、docs 和项目 Skill",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw_targets = args.paths or list(DEFAULT_TARGETS)
    targets = [(PROJECT_ROOT / raw_path).resolve() for raw_path in raw_targets]
    files = _iter_text_files(targets)

    failures: list[str] = []
    for file_path in files:
        issues = _scan_file(file_path)
        if issues:
            relative_path = file_path.relative_to(PROJECT_ROOT)
            failures.append(f"- {relative_path}: {'; '.join(issues)}")

    if failures:
        print("发现疑似中文编码问题：")
        print("\n".join(failures))
        print(
            "\n如果 Get-Content -Encoding UTF8 正常但默认读取乱码，请先运行 .\\scripts\\enable_utf8_console.ps1。"
        )
        return 1

    print(f"text encoding ok: checked {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
