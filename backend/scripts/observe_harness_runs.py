"""汇总 Harness 运行 manifest，形成趋势与恢复能力观测报告。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from harness_run_manifest import validate_manifest
except ModuleNotFoundError:
    from scripts.harness_run_manifest import validate_manifest  # type: ignore[no-redef]

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DIRECTORY = ROOT_DIR / "backend" / "reports" / "harness"


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def discover_manifests(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(path for path in directory.rglob("*.run.json") if path.is_file())


def load_runs(paths: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    runs: list[dict[str, Any]] = []
    issues: list[str] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"{path}: {exc}")
            continue
        if not isinstance(payload, dict):
            issues.append(f"{path}: manifest 根节点不是对象")
            continue
        manifest_issues = validate_manifest(payload)
        if manifest_issues:
            issues.extend(f"{path}: {issue}" for issue in manifest_issues)
            continue
        payload["_path"] = str(path)
        runs.append(payload)
    return runs, issues


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _percentile(values: list[int], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(len(ordered) * percentile) - 1)
    return float(ordered[index])


def summarize_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(run.get("status") or "unknown") for run in runs)
    failure_classes = Counter(str(run.get("failure_class") or "none") for run in runs)
    assertions = [
        run.get("assertions") for run in runs if isinstance(run.get("assertions"), dict)
    ]
    latencies = [
        int(run["latency_ms"]) for run in runs if isinstance(run.get("latency_ms"), int)
    ]
    tool_calls = [
        int(run.get("episode", {}).get("tool_call_count", 0))
        for run in runs
        if isinstance(run.get("episode"), dict)
    ]
    replayable = sum(1 for run in runs if run.get("replayable") is True)
    policy_compliant = sum(
        1 for item in assertions if item.get("policy_compliant") is True
    )
    evidence_complete = sum(
        1 for item in assertions if item.get("evidence_complete") is True
    )
    human_intervened = sum(1 for run in runs if run.get("human_intervention") is True)
    recovery_points = sum(
        1
        for run in runs
        if isinstance(run.get("episode"), dict)
        and str(run["episode"].get("recovery_point") or "").strip()
    )
    known_ids = {str(run.get("run_id")) for run in runs}
    parent_links = sum(
        1
        for run in runs
        if run.get("parent_run_id") and str(run.get("parent_run_id")) in known_ids
    )
    return {
        "total_runs": len(runs),
        "statuses": dict(sorted(statuses.items())),
        "failure_classes": dict(sorted(failure_classes.items())),
        "replayable_ratio": _ratio(replayable, len(runs)),
        "policy_compliant_ratio": _ratio(policy_compliant, len(assertions)),
        "evidence_complete_ratio": _ratio(evidence_complete, len(assertions)),
        "human_intervention_rate": _ratio(human_intervened, len(runs)),
        "average_latency_ms": round(sum(latencies) / len(latencies), 2)
        if latencies
        else None,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "average_tool_calls": round(sum(tool_calls) / len(tool_calls), 2)
        if tool_calls
        else 0.0,
        "recovery_point_coverage": _ratio(recovery_points, len(runs)),
        "parent_link_coverage": _ratio(
            parent_links, sum(1 for run in runs if run.get("parent_run_id"))
        ),
    }


def build_report(
    paths: list[Path], baseline: dict[str, Any] | None = None
) -> dict[str, Any]:
    runs, issues = load_runs(paths)
    metrics = summarize_runs(runs)
    baseline_metrics = baseline.get("metrics", {}) if isinstance(baseline, dict) else {}
    deltas = {
        key: round(value - baseline_metrics[key], 4)
        for key, value in metrics.items()
        if isinstance(value, (int, float))
        and isinstance(baseline_metrics.get(key), (int, float))
    }
    return {
        "schema_version": "1.0",
        "observation_type": "harness_runtime_observation",
        "generated_at": utc_now(),
        "window": {
            "from": min((run.get("generated_at", "") for run in runs), default=None),
            "to": max((run.get("generated_at", "") for run in runs), default=None),
        },
        "source_paths": [str(path) for path in paths],
        "status": "passed" if not issues else "failed",
        "issues": issues,
        "metrics": metrics,
        "trend": {"baseline_present": bool(baseline_metrics), "deltas": deltas},
        "recovery": {
            "recovery_point_coverage": metrics["recovery_point_coverage"],
            "parent_link_coverage": metrics["parent_link_coverage"],
        },
        "otel_attributes": {
            "service.name": "yunxi-harness",
            "gen_ai.operation.name": "harness.run.observation",
            "yunxi.harness.run_count": metrics["total_runs"],
            "yunxi.harness.replayable_ratio": metrics["replayable_ratio"],
            "yunxi.harness.failure_classes": metrics["failure_classes"],
        },
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"拒绝覆盖已有 Harness 观测报告: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="汇总 Harness 运行 manifest")
    parser.add_argument("--directory", action="append", type=Path, default=[])
    parser.add_argument("--manifest", action="append", type=Path, default=[])
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(sys.argv[1:] if argv is None else argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = list(args.manifest)
    for directory in args.directory or [DEFAULT_DIRECTORY]:
        paths.extend(discover_manifests(directory))
    paths = sorted(set(path.resolve() for path in paths))
    baseline = None
    try:
        if args.baseline:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8-sig"))
        report = build_report(paths, baseline)
        if args.output:
            write_report(args.output, report)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[Harness 运行观测] FAIL {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        metrics = report["metrics"]
        print(
            f"harness_observation status={report['status']} runs={metrics['total_runs']} replayable={metrics['replayable_ratio']} recovery={metrics['recovery_point_coverage']} failed={len(report['issues'])}"
        )
    else:
        print(
            f"[Harness 运行观测] {'PASS' if report['status'] == 'passed' else 'FAIL'} runs={report['metrics']['total_runs']}"
        )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
