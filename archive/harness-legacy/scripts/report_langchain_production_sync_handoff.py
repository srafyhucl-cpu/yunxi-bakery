"""生成 LangChain 生产同步 P14 诊断和交接报告。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts import check_langchain_production_observability_release as release_check  # noqa: E402
from scripts import check_langchain_production_runtime_version as runtime_check  # noqa: E402

DEFAULT_RELEASE_REPORT_PATH = release_check.DEFAULT_RELEASE_REPORT_PATH
DEFAULT_TARGET_REMOTE_NAMES = ("origin", "server")
REMOTE_MASTER_REF = "refs/heads/master"
UNKNOWN_VALUE = "unknown"


@dataclass(frozen=True)
class GitRefStatus:
    name: str
    commit: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "commit": self.commit,
            "detail": self.detail,
        }


def build_production_sync_handoff_report(
    *,
    release_report_path: Path,
    local_commit: str | None = None,
    remote_refs: tuple[GitRefStatus, ...] | None = None,
    runtime_report: dict[str, object] | None = None,
    ssh_status: str = "not_checked",
    ssh_detail: str = "",
) -> dict[str, object]:
    expected_version = release_check.read_expected_version()
    current_local_commit = local_commit or read_local_commit()
    current_remote_refs = (
        remote_refs
        if remote_refs is not None
        else tuple(read_remote_ref(name) for name in DEFAULT_TARGET_REMOTE_NAMES)
    )
    release_report = release_check.build_production_observability_release_report(
        release_report_path,
        expected_version=expected_version,
    )
    current_runtime_report = (
        runtime_report
        if runtime_report is not None
        else asyncio_run_runtime_check(expected_version)
    )
    blockers = collect_sync_blockers(
        release_report=release_report,
        runtime_report=current_runtime_report,
        local_commit=current_local_commit,
        remote_refs=current_remote_refs,
        ssh_status=ssh_status,
    )
    return {
        "status": "passed" if not blockers else "blocked",
        "generated_at": utc_now(),
        "trace_id": "20260709-langchain-ai-layer-production-enhancement",
        "phase": "P14-production-version-sync",
        "expected_version": expected_version,
        "target_commit": current_local_commit,
        "release_report": str(release_report_path),
        "release_check": release_report,
        "runtime_check": current_runtime_report,
        "remote_refs": [ref.to_dict() for ref in current_remote_refs],
        "ssh": {
            "status": ssh_status,
            "detail": ssh_detail,
        },
        "blockers": blockers,
        "manual_actions": build_manual_actions(
            target_commit=current_local_commit,
            expected_version=expected_version,
            release_report_path=release_report_path,
        ),
        "post_sync_verification": build_post_sync_verification_commands(),
    }


def collect_sync_blockers(
    *,
    release_report: dict[str, object],
    runtime_report: dict[str, object],
    local_commit: str,
    remote_refs: tuple[GitRefStatus, ...],
    ssh_status: str,
) -> list[dict[str, object]]:
    blockers: list[dict[str, object]] = []
    if release_report.get("status") != "passed":
        blockers.append(
            {
                "code": "production_release_not_ready",
                "message": "P13b 生产发布证据仍未通过。",
                "detail": {
                    "failed": release_report.get("failed", 0),
                    "finding_codes": [
                        finding.get("code")
                        for finding in release_check.list_value(
                            release_report,
                            "findings",
                        )
                        if isinstance(finding, dict)
                    ],
                },
            }
        )
    if runtime_report.get("status") != "passed":
        blockers.append(
            {
                "code": "production_runtime_version_mismatch",
                "message": "生产 /health 或 /ready 真实版本未切到目标版本。",
                "detail": {
                    "expected_version": runtime_report.get("expected_version", ""),
                    "endpoint_versions": runtime_report.get("endpoint_versions", {}),
                    "failed_names": runtime_report.get("failed_names", []),
                },
            }
        )
    for ref_status in remote_refs:
        if ref_status.commit != local_commit:
            blockers.append(
                {
                    "code": "remote_ref_mismatch",
                    "message": f"{ref_status.name}/master 未指向目标 commit。",
                    "detail": {
                        "remote": ref_status.name,
                        "remote_commit": ref_status.commit,
                        "target_commit": local_commit,
                        "detail": ref_status.detail,
                    },
                }
            )
    if ssh_status not in {"available", "not_checked"}:
        blockers.append(
            {
                "code": "server_ssh_unavailable",
                "message": "当前无法通过非交互 SSH 检查或重启生产服务。",
                "detail": {"ssh_status": ssh_status},
            }
        )
    return blockers


def build_manual_actions(
    *,
    target_commit: str,
    expected_version: str,
    release_report_path: Path,
) -> list[str]:
    return [
        "用具备生产权限的账号登录服务器。",
        "cd /opt/apps/yunxibakebot",
        "git status --short",
        f"git rev-parse HEAD  # 目标应为 {target_commit}",
        f"cat VERSION  # 目标应为 {expected_version}",
        "如 commit 或 VERSION 不一致，先按服务器既有部署流程 fast-forward 到目标 commit；不要放宽 callback 或版本门禁。",
        "sudo systemctl restart yunxibakebot",
        "systemctl is-active yunxibakebot",
        "curl -sS https://yunxifood.cn/health",
        "curl -sS https://yunxifood.cn/ready",
        (
            "python scripts\\check_langchain_ai_layer_release_gate.py "
            "--include-production-smoke --include-observability-evidence "
            f"--json-out {release_report_path} --summary"
        ),
        (
            "python scripts\\check_langchain_production_observability_release.py "
            f"--report {release_report_path} --summary"
        ),
    ]


def build_post_sync_verification_commands() -> list[str]:
    return [
        "python scripts\\check_langchain_production_runtime_version.py --summary",
        "python scripts\\check_langchain_ai_layer_release_gate.py --include-production-smoke --include-observability-evidence --json-out reports\\agent-eval\\langchain-ai-layer-release-gate-with-production-observability-latest.json --summary",
        "python scripts\\check_langchain_production_observability_release.py --report reports\\agent-eval\\langchain-ai-layer-release-gate-with-production-observability-latest.json --summary",
        "python scripts\\report_langchain_production_callback_failures.py --json-out reports\\harness\\langchain-production-callback-failures-latest.json --summary",
        "python scripts\\check_project.py --skip-tests",
        "python scripts\\check_evidence_index.py --summary",
    ]


def read_local_commit() -> str:
    return run_git_command(("git", "rev-parse", "HEAD"))


def read_remote_ref(remote_name: str) -> GitRefStatus:
    completed = subprocess.run(
        ("git", "-c", "http.version=HTTP/1.1", "ls-remote", remote_name, "master"),
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return GitRefStatus(
            name=remote_name,
            commit=UNKNOWN_VALUE,
            detail=(completed.stderr or completed.stdout).strip(),
        )
    first_line = completed.stdout.strip().splitlines()[0] if completed.stdout else ""
    parts = first_line.split()
    if len(parts) < 2 or parts[1] != REMOTE_MASTER_REF:
        return GitRefStatus(
            name=remote_name,
            commit=UNKNOWN_VALUE,
            detail=completed.stdout.strip(),
        )
    return GitRefStatus(name=remote_name, commit=parts[0], detail="ok")


def run_git_command(command: tuple[str, ...]) -> str:
    completed = subprocess.run(
        command,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return UNKNOWN_VALUE
    return completed.stdout.strip()


def asyncio_run_runtime_check(expected_version: str) -> dict[str, object]:
    import asyncio

    return asyncio.run(
        runtime_check.build_runtime_version_report(expected_version=expected_version)
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build LangChain production sync handoff report"
    )
    parser.add_argument(
        "--release-report",
        type=Path,
        default=DEFAULT_RELEASE_REPORT_PATH,
        help="显式生产 release gate JSON 报告路径",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument("--json-out", type=Path, help="写入 JSON 报告路径")
    parser.add_argument(
        "--ssh-status",
        default="not_checked",
        choices=("not_checked", "available", "permission_denied", "timeout"),
        help="当前生产 SSH 检查状态，只记录诊断结果，不执行 SSH。",
    )
    parser.add_argument("--ssh-detail", default="", help="SSH 失败或跳过原因")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_production_sync_handoff_report(
        release_report_path=args.release_report,
        ssh_status=args.ssh_status,
        ssh_detail=args.ssh_detail,
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print_summary(report)
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_summary(report: dict[str, object]) -> None:
    release_check_report = release_check.dict_value(report, "release_check")
    production = release_check.dict_value(release_check_report, "production")
    runtime_report = release_check.dict_value(report, "runtime_check")
    print(
        "langchain_production_sync_handoff "
        f"status={report['status']} blockers={len(report['blockers'])} "
        f"target_commit={report['target_commit']} "
        f"expected_version={report['expected_version']} "
        f"runtime_status={runtime_report.get('status', 'missing')} "
        f"callback_failed={production.get('callback_failed', 0)}"
    )
    for blocker in release_check.list_value(report, "blockers"):
        if isinstance(blocker, dict):
            print(f"BLOCK {blocker.get('code')}: {blocker.get('message')}")


def print_text_report(report: dict[str, object]) -> None:
    print("langchain_production_sync_handoff")
    print(f"status={report['status']} blockers={len(report['blockers'])}")
    print(f"target_commit={report['target_commit']}")
    print(f"expected_version={report['expected_version']}")
    for action in release_check.list_value(report, "manual_actions"):
        print(f"- {action}")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
