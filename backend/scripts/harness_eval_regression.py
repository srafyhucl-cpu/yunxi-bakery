"""运行 Harness 自评回归集并输出可比较的质量基线。"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from check_chinese_governance import build_report as build_chinese_report
    from check_evidence_index import check_evidence_index
    from check_project_development_register import parse_register
    from harness_policy import (
        check_operation,
        load_policy,
        policy_hash,
    )
    from harness_run_manifest import build_manifest, validate_manifest
    import harness_p0_gate
except ModuleNotFoundError:
    from scripts.check_chinese_governance import build_report as build_chinese_report
    from scripts.check_evidence_index import check_evidence_index
    from scripts.check_project_development_register import parse_register
    from scripts.harness_policy import (  # type: ignore[no-redef]
        check_operation,
        load_policy,
        policy_hash,
    )
    from scripts.harness_run_manifest import build_manifest, validate_manifest  # type: ignore[no-redef]
    from scripts import harness_p0_gate  # type: ignore[no-redef]

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = (
    ROOT_DIR / "docs" / "harness-engineering" / "evals" / "harness-eval-dataset.json"
)
EXPECTED_P0_GATE_CHECK_NAMES = (
    "依赖锁一致性",
    "中文治理 P0",
    "策略即代码 P0",
    "运行 manifest P0",
    "项目开发总表",
    "错误账本",
    "证据索引",
    "文本编码",
    "项目红线",
)
EVALUATOR_VERSION = "1.0.0"


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def load_dataset(path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("Harness 评测数据集必须包含 cases 数组")
    return payload


def _passed(name: str, details: str = "") -> dict[str, Any]:
    return {
        "evaluator": name,
        "passed": True,
        "failure_class": "none",
        "details": details,
    }


def _failed(name: str, details: str) -> dict[str, Any]:
    return {
        "evaluator": name,
        "passed": False,
        "failure_class": "assertion_failed",
        "details": details,
    }


def evaluate_status_label_contract(root_dir: Path) -> dict[str, Any]:
    result = parse_register(root_dir / "PROJECT-STATE.md")
    return (
        _passed("status_label_contract")
        if result.passed
        else _failed("status_label_contract", "；".join(result.issues))
    )


def evaluate_policy_boundary(root_dir: Path) -> dict[str, Any]:
    policy = load_policy(
        root_dir / "docs" / "harness-engineering" / "core" / "harness-policy.json"
    )
    recursive_issues = check_operation("recursive_delete", policy, human_approved=False)
    rebuildable_issues = check_operation(
        "rebuildable_cleanup", policy, human_approved=False
    )
    approved_issues = check_operation(
        "rebuildable_cleanup", policy, human_approved=True
    )
    if not recursive_issues or not rebuildable_issues or approved_issues:
        return _failed("policy_boundary", "高风险操作阻断或批准逻辑不符合预期")
    return _passed("policy_boundary")


def evaluate_manifest_replay_contract(root_dir: Path) -> dict[str, Any]:
    manifest = build_manifest(
        task_id="T-HARNESS-EVAL-REGRESSION",
        trace_id="20260831-harness-eval-regression",
        goal="验证 Harness 运行契约",
        status="active",
        model_id="self-eval",
        replayable=True,
        plan_summary="执行最小 Harness 自评",
        recovery_point="从策略边界测试继续",
        verification=["自评合同检查"],
        evidence=["内存测试证据"],
        root_dir=root_dir,
    )
    issues = validate_manifest(manifest)
    episode = manifest.get("episode")
    if issues or not isinstance(episode, dict) or not episode.get("recovery_point"):
        return _failed(
            "manifest_replay_contract",
            "；".join(issues) or "episode 缺少 recovery_point",
        )
    return _passed("manifest_replay_contract")


def evaluate_evidence_index_integrity(root_dir: Path) -> dict[str, Any]:
    result = check_evidence_index(
        root_dir / "docs" / "harness-engineering" / "core" / "evidence-index.md"
    )
    return (
        _passed("evidence_index_integrity", f"entries={len(result.entries)}")
        if result.passed
        else _failed("evidence_index_integrity", "；".join(result.issues))
    )


def evaluate_chinese_governance_coverage(root_dir: Path) -> dict[str, Any]:
    report = build_chinese_report(root_dir)
    coverage = report.get("coverage", {})
    passed = report.get("status") == "passed" and coverage.get("ratio") == 1.0
    return (
        _passed("chinese_governance_coverage", f"coverage={coverage.get('ratio', 0)}")
        if passed
        else _failed("chinese_governance_coverage", "中文治理检查未通过")
    )


def evaluate_p0_gate_contract(root_dir: Path) -> dict[str, Any]:
    del root_dir
    commands = harness_p0_gate.build_commands()
    names = [name for name, _ in commands]
    return (
        _passed("p0_gate_contract", f"checks={len(EXPECTED_P0_GATE_CHECK_NAMES)}")
        if names == list(EXPECTED_P0_GATE_CHECK_NAMES)
        else _failed("p0_gate_contract", f"实际检查={names}")
    )


def evaluate_recovery_point_contract(root_dir: Path) -> dict[str, Any]:
    del root_dir
    with tempfile.TemporaryDirectory(
        prefix=".tmp-harness-eval-recovery-", dir=ROOT_DIR.parent
    ) as directory:
        recovery = Path(directory) / "recovery.json"
        recovery.write_text(
            json.dumps({"recovery_point": "继续执行未完成检查", "replayable": True}),
            encoding="utf-8",
        )
        payload = json.loads(recovery.read_text(encoding="utf-8"))
    return (
        _passed("recovery_point_contract")
        if payload.get("recovery_point") and payload.get("replayable") is True
        else _failed("recovery_point_contract", "恢复点不可读取")
    )


def evaluate_policy_hash_stability(root_dir: Path) -> dict[str, Any]:
    policy_path = (
        root_dir / "docs" / "harness-engineering" / "core" / "harness-policy.json"
    )
    policy = load_policy(policy_path)
    first = policy_hash(policy)
    second = policy_hash(load_policy(policy_path))
    return (
        _passed("policy_hash_stability", f"sha256={first}")
        if first == second
        else _failed("policy_hash_stability", "策略哈希重复计算不一致")
    )


EVALUATORS: dict[str, Callable[[Path], dict[str, Any]]] = {
    "status_label_contract": evaluate_status_label_contract,
    "policy_boundary": evaluate_policy_boundary,
    "manifest_replay_contract": evaluate_manifest_replay_contract,
    "evidence_index_integrity": evaluate_evidence_index_integrity,
    "chinese_governance_coverage": evaluate_chinese_governance_coverage,
    "p0_gate_contract": evaluate_p0_gate_contract,
    "recovery_point_contract": evaluate_recovery_point_contract,
    "policy_hash_stability": evaluate_policy_hash_stability,
}


def evaluate_dataset(
    dataset: dict[str, Any], root_dir: Path = ROOT_DIR
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case in dataset["cases"]:
        if not isinstance(case, dict):
            results.append(_failed("invalid_case", "评测用例不是对象"))
            continue
        evaluator_name = str(case.get("evaluator") or "")
        evaluator = EVALUATORS.get(evaluator_name)
        if evaluator is None:
            result = _failed(evaluator_name or "unknown", "未注册的评估器")
        else:
            try:
                result = evaluator(root_dir)
            except (OSError, ValueError, KeyError) as exc:
                result = _failed(evaluator_name, str(exc))
                result["failure_class"] = "evaluator_error"
        result.update(
            {"case_id": case.get("case_id", ""), "category": case.get("category", "")}
        )
        results.append(result)
    passed = sum(1 for result in results if result["passed"] is True)
    total = len(results)
    return {
        "schema_version": "1.0",
        "evaluation_type": "harness_regression",
        "dataset_version": str(dataset.get("dataset_version") or "unknown"),
        "evaluator_version": EVALUATOR_VERSION,
        "generated_at": utc_now(),
        "threshold": 1.0,
        "summary": {
            "passed": passed,
            "total": total,
            "ratio": round(passed / total, 4) if total else 0.0,
            "failure_classes": {
                failure_class: sum(
                    1
                    for result in results
                    if result.get("failure_class") == failure_class
                )
                for failure_class in sorted(
                    {
                        str(result.get("failure_class") or "unknown")
                        for result in results
                    }
                )
            },
        },
        "status": "passed" if total and passed == total else "failed",
        "results": results,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"拒绝覆盖已有 Harness 自评报告: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 Harness 自评回归集")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(sys.argv[1:] if argv is None else argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        baseline = None
        if args.baseline:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8-sig"))
        report = evaluate_dataset(load_dataset(args.dataset), ROOT_DIR)
        baseline_summary = (
            baseline.get("summary", {}) if isinstance(baseline, dict) else {}
        )
        report["trend"] = {
            "baseline_present": bool(baseline_summary),
            "baseline_ratio": baseline_summary.get("ratio"),
            "ratio_delta": (
                round(report["summary"]["ratio"] - baseline_summary["ratio"], 4)
                if isinstance(baseline_summary.get("ratio"), (int, float))
                else None
            ),
        }
        if args.output:
            write_report(args.output, report)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[Harness 自评] FAIL {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        summary = report["summary"]
        print(
            f"harness_eval status={report['status']} passed={summary['passed']} total={summary['total']} ratio={summary['ratio']}"
        )
    elif report["status"] == "failed":
        print("[Harness 自评] FAIL")
        for result in report["results"]:
            if not result["passed"]:
                print(f"  - {result['case_id']}: {result['details']}")
    else:
        print(f"[Harness 自评] PASS cases={report['summary']['total']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
