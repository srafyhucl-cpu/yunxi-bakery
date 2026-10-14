"""真实脱敏会话 replay 接入准备度检查。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from app.service.agents.evaluation import write_json_report  # noqa: E402
from scripts.check_real_conversation_replay_pool import (  # noqa: E402
    DEFAULT_POOL_MANIFEST_PATH,
    build_real_replay_pool_report,
)

DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "reports" / "agent-eval" / "real-conversation-replay-intake.json"
)
REQUIRED_ARTIFACTS = (
    "scripts/check_real_conversation_replay.py",
    "scripts/export_real_conversation_replay_fixture.py",
    "scripts/check_real_conversation_replay_coverage.py",
    "scripts/build_real_conversation_replay_intake_packet.py",
    "scripts/prepare_real_conversation_replay_pool_entry.py",
    "scripts/check_real_conversation_replay_pool.py",
    "tests/fixtures/customer_real_replay_pool_manifest_sample.json",
)


def build_real_replay_intake_readiness_report(
    *,
    manifest_path: Path = DEFAULT_POOL_MANIFEST_PATH,
    require_real: bool = False,
) -> dict[str, object]:
    artifacts = build_artifact_checks()
    pool_report = build_real_replay_pool_report(
        manifest_path=manifest_path,
        require_real=False,
    )
    real_sample_ready = bool(pool_report.get("real_pool_ready"))
    missing_actions = build_missing_actions(
        pool_report=pool_report,
        real_sample_ready=real_sample_ready,
    )
    failed = count_failed_checks(
        artifacts=artifacts,
        pool_report=pool_report,
        require_real=require_real,
        real_sample_ready=real_sample_ready,
    )
    return {
        "status": "passed" if failed == 0 else "failed",
        "generated_at": utc_now(),
        "app_version": APP_VERSION,
        "manifest": str(manifest_path),
        "require_real": require_real,
        "real_sample_ready": real_sample_ready,
        "failed": failed,
        "artifacts": artifacts,
        "pool": summarize_pool_report(pool_report),
        "missing_actions": missing_actions,
        "boundaries": {
            "real_customer_data_committed": False,
            "raw_customer_conversation_read": False,
            "business_database_read": False,
            "external_llm_called": False,
            "synthetic_samples_count_as_real": False,
        },
    }


def build_artifact_checks() -> list[dict[str, object]]:
    checks = []
    for raw_path in REQUIRED_ARTIFACTS:
        path = ROOT_DIR / raw_path
        checks.append(
            {
                "path": raw_path,
                "exists": path.exists(),
                "status": "passed" if path.exists() else "failed",
            }
        )
    return checks


def build_missing_actions(
    *,
    pool_report: dict[str, object],
    real_sample_ready: bool,
) -> list[str]:
    actions = []
    if pool_report.get("status") != "passed":
        actions.append("fix_real_replay_pool_manifest_or_fixture")
    if not real_sample_ready:
        actions.extend(
            [
                "collect_real_customer_conversations_outside_repo",
                "redact_real_conversations_and_keep_raw_source_not_committed",
                "add_real_replay_pool_manifest_entry_with_redaction_proof",
                "run_real_replay_pool_with_require_real",
            ]
        )
    return actions


def count_failed_checks(
    *,
    artifacts: list[dict[str, object]],
    pool_report: dict[str, object],
    require_real: bool,
    real_sample_ready: bool,
) -> int:
    failed = sum(1 for item in artifacts if item.get("status") != "passed")
    if pool_report.get("status") != "passed":
        failed += 1
    if require_real and not real_sample_ready:
        failed += 1
    return failed


def summarize_pool_report(pool_report: dict[str, object]) -> dict[str, object]:
    return {
        "status": pool_report.get("status", "missing"),
        "total": pool_report.get("total", 0),
        "failed": pool_report.get("failed", 0),
        "real_entries": pool_report.get("real_entries", 0),
        "synthetic_entries": pool_report.get("synthetic_entries", 0),
        "real_pool_ready": pool_report.get("real_pool_ready", False),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check real conversation replay intake readiness"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="写入真实样本接入准备度 JSON 路径",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_POOL_MANIFEST_PATH,
        help="真实脱敏 replay 样本池 manifest",
    )
    parser.add_argument(
        "--require-real",
        action="store_true",
        help="要求真实脱敏样本池已经就绪；合成样例不能满足该门禁",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_real_replay_intake_readiness_report(
        manifest_path=args.manifest,
        require_real=args.require_real,
    )
    if args.json_out is not None:
        write_json_report(report, args.json_out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print(
            "real_conversation_replay_intake "
            f"status={report['status']} "
            f"real_sample_ready={str(report['real_sample_ready']).lower()} "
            f"missing_actions={len(report['missing_actions'])}"
        )
    else:
        print_text_report(report)
    return 0 if report["status"] == "passed" else 1


def print_text_report(report: dict[str, object]) -> None:
    print("real_conversation_replay_intake")
    print(
        f"status={report['status']} "
        f"real_sample_ready={report['real_sample_ready']} "
        f"failed={report['failed']}"
    )
    for action in report["missing_actions"]:
        print(f"NEXT {action}")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
