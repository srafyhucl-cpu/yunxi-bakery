"""批量校验 Harness 运行 manifest，并检查活动任务是否有记录。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from harness_run_manifest import validate_manifest
except ModuleNotFoundError:
    from scripts.harness_run_manifest import validate_manifest  # type: ignore[no-redef]

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = ROOT_DIR / "backend" / "reports" / "harness"


def discover_manifests(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(path for path in directory.rglob("*.run.json") if path.is_file())


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("manifest 根节点必须是对象")
    return payload


def check_manifests(
    paths: list[Path],
    *,
    active_task_ids: set[str] | None = None,
) -> dict[str, object]:
    issues: list[str] = []
    reports: list[dict[str, object]] = []
    seen_tasks: set[str] = set()
    for path in paths:
        try:
            payload = load_manifest(path)
            manifest_issues = validate_manifest(payload)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            manifest_issues = [str(exc)]
            payload = {}
        task_id = str(payload.get("task_id") or "")
        if task_id:
            seen_tasks.add(task_id)
        if manifest_issues:
            issues.extend(f"{path}: {issue}" for issue in manifest_issues)
        reports.append(
            {
                "path": str(path),
                "run_id": str(payload.get("run_id") or ""),
                "task_id": task_id,
                "status": "passed" if not manifest_issues else "failed",
                "issues": manifest_issues,
            }
        )
    missing_tasks = sorted((active_task_ids or set()) - seen_tasks)
    issues.extend(f"活动任务缺少运行 manifest: {task_id}" for task_id in missing_tasks)
    return {
        "status": "passed" if not issues else "failed",
        "total": len(paths),
        "failed": len(issues),
        "missing_active_tasks": missing_tasks,
        "issues": issues,
        "manifests": reports,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量检查 Harness 运行 manifest")
    parser.add_argument("--manifest", action="append", type=Path, default=[])
    parser.add_argument("--directory", action="append", type=Path, default=[])
    parser.add_argument(
        "--require-active-tasks",
        action="store_true",
        help="要求 PROJECT-STATE 中 active 任务至少有一个运行 manifest",
    )
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _active_task_ids() -> set[str]:
    state_path = ROOT_DIR / "PROJECT-STATE.md"
    if not state_path.exists():
        return set()
    text = state_path.read_text(encoding="utf-8-sig")
    import re

    return {
        task_id
        for task_id, status in re.findall(
            r"^\|\s*([A-Z0-9][A-Z0-9_-]*)\s*\|.*?\|\s*(active)\s*\|",
            text,
            flags=re.MULTILINE,
        )
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    paths = list(args.manifest)
    directories = args.directory or [DEFAULT_REPORT_DIR]
    for directory in directories:
        paths.extend(discover_manifests(directory))
    paths = sorted(set(path.resolve() for path in paths))
    report = check_manifests(
        paths,
        active_task_ids=_active_task_ids() if args.require_active_tasks else set(),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "harness_manifest_check "
            f"status={report['status']} total={report['total']} "
            f"failed={report['failed']} "
            f"missing_active_tasks={len(report['missing_active_tasks'])}"
        )
    elif report["issues"]:
        print("[Harness manifest] FAIL")
        for issue in report["issues"]:
            print(f"  - {issue}")
    else:
        print(f"[Harness manifest] PASS total={report['total']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
