"""检查生产与开发依赖锁的共享包版本是否一致。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_PRODUCTION_LOCK = ROOT_DIR / "backend" / "requirements.txt"
DEFAULT_DEVELOPMENT_LOCK = ROOT_DIR / "backend" / "requirements-dev.txt"
DEFAULT_DEVELOPMENT_INPUT = ROOT_DIR / "backend" / "requirements-dev.in"
PIN_RE = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==([^\s;]+)")


class RequirementsLockError(ValueError):
    """依赖锁或其输入文件不符合一致性约定。"""


def normalise_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_pins(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise RequirementsLockError(f"无法读取依赖锁: {path}: {exc}") from exc
    pins: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        match = PIN_RE.match(line.strip())
        if not match:
            continue
        name = normalise_package_name(match.group(1))
        version = match.group(2)
        previous = pins.get(name)
        if previous and previous != version:
            raise RequirementsLockError(
                f"{path}:{line_number}: 包 {name} 存在冲突版本 {previous} 与 {version}"
            )
        pins[name] = version
    if not pins:
        raise RequirementsLockError(f"依赖锁未包含固定版本: {path}")
    return pins


def check_development_input(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        return [f"无法读取开发依赖输入: {path}: {exc}"]
    if any(line.strip() == "-c requirements.txt" for line in lines):
        return []
    return [f"开发依赖输入缺少生产锁约束: {path}"]


def build_report(
    production_lock: Path = DEFAULT_PRODUCTION_LOCK,
    development_lock: Path = DEFAULT_DEVELOPMENT_LOCK,
    development_input: Path = DEFAULT_DEVELOPMENT_INPUT,
) -> dict[str, object]:
    production = read_pins(production_lock)
    development = read_pins(development_lock)
    shared = sorted(set(production) & set(development))
    issues = [
        f"共享依赖版本不一致: {name} (production={production[name]}, development={development[name]})"
        for name in shared
        if production[name] != development[name]
    ]
    issues.extend(check_development_input(development_input))
    return {
        "status": "passed" if not issues else "failed",
        "production_lock": str(production_lock),
        "development_lock": str(development_lock),
        "development_input": str(development_input),
        "production_pins": len(production),
        "development_pins": len(development),
        "shared_pins": len(shared),
        "issues": issues,
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(f"拒绝覆盖依赖锁检查报告: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查生产与开发依赖锁一致性")
    parser.add_argument("--production-lock", type=Path, default=DEFAULT_PRODUCTION_LOCK)
    parser.add_argument(
        "--development-lock", type=Path, default=DEFAULT_DEVELOPMENT_LOCK
    )
    parser.add_argument(
        "--development-input", type=Path, default=DEFAULT_DEVELOPMENT_INPUT
    )
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = build_report(
            args.production_lock,
            args.development_lock,
            args.development_input,
        )
        if args.json_out:
            write_json(args.json_out, report)
    except (OSError, RequirementsLockError, FileExistsError) as exc:
        print(f"[依赖锁] FAIL {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "requirements_lock_alignment "
            f"status={report['status']} shared={report['shared_pins']} "
            f"failed={len(report['issues'])}"
        )
    elif report["issues"]:
        print("[依赖锁] FAIL")
        for issue in report["issues"]:
            print(f"  - {issue}")
    else:
        print(f"[依赖锁] PASS shared={report['shared_pins']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
