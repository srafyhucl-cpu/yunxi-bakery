"""检查 Harness 策略快照、敏感路径和高风险操作。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from harness_policy import (
        DEFAULT_POLICY_PATH,
        PolicyError,
        build_policy_snapshot,
        check_operation,
        check_paths,
        load_policy,
        normalise_repo_path,
        policy_hash,
    )
except ModuleNotFoundError:
    from scripts.harness_policy import (  # type: ignore[no-redef]
        DEFAULT_POLICY_PATH,
        PolicyError,
        build_policy_snapshot,
        check_operation,
        check_paths,
        load_policy,
        normalise_repo_path,
        policy_hash,
    )

ROOT_DIR = Path(__file__).resolve().parents[2]


def _git_paths(args: list[str], root_dir: Path = ROOT_DIR) -> list[str]:
    """读取 Git 变更路径，兼容空格和中文文件名。"""
    completed = subprocess.run(
        ["git", *args],
        cwd=root_dir,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        command = " ".join(("git", *args))
        raise PolicyError(
            f"Git 变更范围读取失败: {command}"
            + (f"; {detail}" if detail else f"; exit={completed.returncode}")
        )
    return [
        item.decode("utf-8", errors="replace")
        for item in completed.stdout.split(b"\0")
        if item
    ]


def collect_changed_paths(
    root_dir: Path = ROOT_DIR,
    *,
    base: str | None = None,
    head: str | None = None,
) -> list[str]:
    """读取指定提交范围的变更；未指定提交时回退到工作区差异。"""
    if base and head:
        verify = subprocess.run(
            ["git", "rev-parse", "--verify", f"{head}^{{commit}}"],
            cwd=root_dir,
            capture_output=True,
            check=False,
        )
        if verify.returncode != 0:
            raise PolicyError(f"Git 目标提交不可用: {head}")
        if set(base) != {"0"}:
            verify_base = subprocess.run(
                ["git", "rev-parse", "--verify", f"{base}^{{commit}}"],
                cwd=root_dir,
                capture_output=True,
                check=False,
            )
            if verify_base.returncode != 0:
                raise PolicyError(f"Git 基线提交不可用: {base}")
        if set(base) == {"0"}:
            tracked = _git_paths(
                [
                    "diff-tree",
                    "--root",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    "-z",
                    head,
                ],
                root_dir,
            )
        else:
            tracked = _git_paths(["diff", "--name-only", "-z", base, head], root_dir)
        untracked: list[str] = []
    else:
        tracked = _git_paths(["diff", "--name-only", "-z", "HEAD"], root_dir)
        untracked = _git_paths(
            ["ls-files", "--others", "--exclude-standard", "-z"],
            root_dir,
        )
    return sorted(
        {normalise_repo_path(path, root_dir) for path in (*tracked, *untracked) if path}
    )


def check_manifest_policy_hash(
    manifest_path: Path,
    policy: dict[str, Any],
) -> list[str]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"无法读取运行 manifest: {manifest_path}: {exc}"]
    if not isinstance(payload, dict):
        return [f"运行 manifest 根节点不是对象: {manifest_path}"]
    expected = policy_hash(policy)
    actual = str(payload.get("tool_policy_hash") or "")
    if actual != expected:
        return [
            f"运行 manifest 策略哈希不一致: {manifest_path} "
            f"(expected={expected}, actual={actual or '<empty>'})"
        ]
    snapshot = payload.get("policy_snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("sha256") != expected:
        return [f"运行 manifest 缺少匹配的 policy_snapshot: {manifest_path}"]
    return []


def build_policy_report(
    *,
    policy_path: Path = DEFAULT_POLICY_PATH,
    paths: list[str] | None = None,
    allowed_patterns: list[str] | None = None,
    operation: str | None = None,
    human_approved: bool = False,
    manifest_paths: list[Path] | None = None,
) -> dict[str, object]:
    policy = load_policy(policy_path)
    checked_paths = sorted(set(paths or []))
    issues = check_paths(checked_paths, policy, allowed_patterns)
    issues.extend(check_operation(operation, policy, human_approved=human_approved))
    for manifest_path in manifest_paths or []:
        issues.extend(check_manifest_policy_hash(manifest_path, policy))
    snapshot = build_policy_snapshot(policy_path)
    return {
        "status": "passed" if not issues else "failed",
        "policy": snapshot,
        "checked_paths": checked_paths,
        "allowed_path_patterns": list(allowed_patterns or []),
        "operation": operation or "",
        "human_approved": human_approved,
        "manifest_paths": [str(path) for path in manifest_paths or []],
        "issues": issues,
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(f"拒绝覆盖已有策略报告: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查 Harness 策略即代码")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--git-diff", action="store_true", help="检查当前 Git 变更路径")
    parser.add_argument("--base", help="Git 变更范围基线提交 SHA")
    parser.add_argument("--head", help="Git 变更范围目标提交 SHA")
    parser.add_argument("--path", action="append", default=[], help="额外检查路径")
    parser.add_argument(
        "--allowed-path",
        action="append",
        default=[],
        help="任务级允许路径模式，可重复传入",
    )
    parser.add_argument("--operation", help="检查一次高风险操作")
    parser.add_argument(
        "--human-approved",
        action="store_true",
        help="明确声明本次操作已获得人工批准",
    )
    parser.add_argument(
        "--manifest",
        action="append",
        default=[],
        type=Path,
        help="检查运行 manifest 中的策略哈希",
    )
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if bool(args.base) != bool(args.head):
            raise PolicyError("--base 与 --head 必须同时提供")
        paths = list(args.path)
        if args.git_diff:
            paths.extend(collect_changed_paths(base=args.base, head=args.head))
        report = build_policy_report(
            policy_path=args.policy,
            paths=paths,
            allowed_patterns=args.allowed_path,
            operation=args.operation,
            human_approved=args.human_approved,
            manifest_paths=args.manifest,
        )
    except (OSError, PolicyError) as exc:
        print(f"[Harness 策略] FAIL {exc}", file=sys.stderr)
        return 1
    if args.json_out:
        try:
            _write_json(args.json_out, report)
        except FileExistsError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "harness_policy "
            f"status={report['status']} "
            f"policy_sha256={report['policy']['sha256']} "
            f"checked_paths={len(report['checked_paths'])} "
            f"failed={len(report['issues'])}"
        )
    elif report["issues"]:
        print("[Harness 策略] FAIL")
        for issue in report["issues"]:
            print(f"  - {issue}")
    else:
        print(
            "[Harness 策略] PASS "
            f"policy_sha256={report['policy']['sha256']} "
            f"checked_paths={len(report['checked_paths'])}"
        )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
