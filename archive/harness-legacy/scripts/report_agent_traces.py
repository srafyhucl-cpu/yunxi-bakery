"""本地 Agent trace 汇总报告。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION  # noqa: E402
from app.service.agents.trace_report import (  # noqa: E402
    build_agent_trace_report,
    parse_trace_runs,
)

DEFAULT_TRACE_DIR = ROOT_DIR / "reports" / "agent-traces"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report local agent traces")
    parser.add_argument("--input", type=Path, help="读取指定 trace JSON 文件")
    parser.add_argument(
        "--latest",
        action="store_true",
        help="读取 reports/agent-traces 下最新 JSON 文件",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--summary", action="store_true", help="只输出摘要")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    input_path = _resolve_input_path(args)
    payload = _load_json(input_path) if input_path is not None else []
    runs = parse_trace_runs(payload)
    report = build_agent_trace_report(
        runs,
        metadata={
            "generated_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "app_version": APP_VERSION,
            "source": str(input_path) if input_path is not None else "",
        },
    ).to_dict()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        print_summary(report)
    else:
        print_text_report(report)
    return 0


def print_summary(report: dict[str, Any]) -> None:
    print(
        "agent_traces "
        f"status={report['status']} total_runs={report['total_runs']} "
        f"agents={len(report['agents'])}"
    )


def print_text_report(report: dict[str, Any]) -> None:
    print("agent_traces")
    print(
        f"status={report['status']} total_runs={report['total_runs']} "
        f"agents={len(report['agents'])}"
    )
    for agent in report["agents"]:
        print(
            "{agent}: runs={run_count} fallback={fallback_count} "
            "tools={tool_call_count} knowledge_hits={knowledge_hit_count} "
            "avg_latency_ms={average_latency_ms}".format(**agent)
        )
        print(f"  nodes={agent['node_counts']}")


def _resolve_input_path(args: argparse.Namespace) -> Path | None:
    if args.input is not None:
        return args.input
    if not args.latest:
        return None
    return _latest_trace_file(DEFAULT_TRACE_DIR)


def _latest_trace_file(trace_dir: Path) -> Path | None:
    if not trace_dir.exists():
        return None
    candidates = [path for path in trace_dir.glob("*.json") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
