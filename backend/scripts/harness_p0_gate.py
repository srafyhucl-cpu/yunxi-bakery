"""Harness P0 统一门禁入口。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    from harness_policy import build_policy_snapshot
except ModuleNotFoundError:
    from scripts.harness_policy import build_policy_snapshot

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
DEFAULT_POLICY = (
    ROOT_DIR / "docs" / "harness-engineering" / "core" / "harness-policy.json"
)


@dataclass(frozen=True)
class GateResult:
    name: str
    command: tuple[str, ...]
    passed: bool
    duration_ms: int
    output: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "command": list(self.command),
            "passed": self.passed,
            "duration_ms": self.duration_ms,
            "output": self.output,
        }


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def build_commands(
    *, base_sha: str | None = None, head_sha: str | None = None
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    python = sys.executable
    policy_command = [
        python,
        "backend/scripts/check_harness_policy.py",
        "--git-diff",
        "--summary",
    ]
    if base_sha and head_sha:
        policy_command.extend(["--base", base_sha, "--head", head_sha])
    return (
        (
            "中文治理 P0",
            (python, "backend/scripts/check_chinese_governance.py", "--summary"),
        ),
        (
            "策略即代码 P0",
            tuple(policy_command),
        ),
        (
            "运行 manifest P0",
            (python, "backend/scripts/check_harness_run_manifest.py", "--summary"),
        ),
        (
            "项目开发总表",
            (python, "backend/scripts/check_project_development_register.py"),
        ),
        (
            "错误账本",
            (python, "backend/scripts/check_mistake_ledger.py"),
        ),
        (
            "证据索引",
            (python, "backend/scripts/check_evidence_index.py", "--summary"),
        ),
        (
            "文本编码",
            (python, "backend/scripts/check_text_encoding.py"),
        ),
        (
            "项目红线",
            (python, "backend/scripts/check_project.py", "--skip-tests"),
        ),
    )


def run_check(
    name: str,
    command: tuple[str, ...],
    *,
    root_dir: Path = ROOT_DIR,
    env: dict[str, str] | None = None,
) -> GateResult:
    started = time.perf_counter()
    completed = subprocess.run(
        list(command),
        cwd=root_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=env,
    )
    duration_ms = round((time.perf_counter() - started) * 1000)
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    return GateResult(name, command, completed.returncode == 0, duration_ms, output)


def run_gate(
    root_dir: Path = ROOT_DIR,
    *,
    base_sha: str | None = None,
    head_sha: str | None = None,
) -> dict[str, object]:
    """运行所有 P0 检查并返回结构化结果。"""
    if bool(base_sha) != bool(head_sha):
        raise ValueError("策略提交范围必须同时提供 base_sha 和 head_sha")
    with tempfile.TemporaryDirectory(
        prefix=".yunxi-harness-p0-", dir=root_dir.parent
    ) as temp_dir:
        env = os.environ.copy()
        env.update(
            {
                "PYTHONUTF8": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "YUNXI_USE_FAKE_EMBEDDING": "1",
                "TMP": temp_dir,
                "TEMP": temp_dir,
                "TMPDIR": temp_dir,
            }
        )
        commands = (
            build_commands(base_sha=base_sha, head_sha=head_sha)
            if base_sha and head_sha
            else build_commands()
        )
        results = [
            run_check(name, command, root_dir=root_dir, env=env)
            for name, command in commands
        ]
    failed = [result for result in results if not result.passed]
    try:
        policy = build_policy_snapshot(DEFAULT_POLICY)
    except (OSError, ValueError) as exc:
        policy = {"policy_id": "", "schema_version": "", "sha256": ""}
        failed = failed + [GateResult("策略快照", ("load_policy",), False, 0, str(exc))]
    return {
        "status": "passed" if not failed else "failed",
        "generated_at": utc_now(),
        "run_id": f"p0-gate-{uuid.uuid4().hex[:16]}",
        "policy_diff_range": {
            "base_sha": base_sha or "",
            "head_sha": head_sha or "",
        },
        "policy_snapshot": policy,
        "checks": [result.to_dict() for result in results],
        "failed": len(failed),
        "issues": [
            {
                "name": result.name,
                "output": result.output,
            }
            for result in failed
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 Harness P0 统一门禁")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--policy-base-sha")
    parser.add_argument("--policy-head-sha")
    return parser.parse_args(sys.argv[1:] if argv is None else argv)


def write_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(f"拒绝覆盖 P0 门禁报告: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run_gate(
            base_sha=args.policy_base_sha,
            head_sha=args.policy_head_sha,
        )
        if args.json_out:
            write_json(args.json_out, report)
    except (OSError, ValueError) as exc:
        print(f"[Harness P0 门禁] FAIL {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "harness_p0_gate "
            f"status={report['status']} checks={len(report['checks'])} "
            f"failed={report['failed']} run_id={report['run_id']}"
        )
    elif report["status"] == "failed":
        print("[Harness P0 门禁] FAIL")
        for issue in report["issues"]:
            print(f"  - {issue['name']}: {issue['output']}")
    else:
        print("[Harness P0 门禁] PASS")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
