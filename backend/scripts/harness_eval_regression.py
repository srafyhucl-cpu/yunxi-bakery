"""运行 Harness 自评回归集并输出可比较的质量基线。"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import yaml

    from build_harness_artifact_index import (
        DEFAULT_REQUIRED_PATTERNS as ARTIFACT_INDEX_REQUIRED_PATTERNS,
    )
    from harness_ci_summary import (
        build_summary as build_ci_summary,
        render_markdown as render_ci_summary,
    )
    from harness_failure_candidate import (
        build_ci_stage_summary,
        build_failure_candidate,
        generate_candidates_from_summary,
        write_candidate,
    )
    from check_chinese_governance import build_report as build_chinese_report
    from check_evidence_index import check_evidence_index
    from check_project_development_register import parse_register
    from harness_policy import (
        check_operation,
        load_policy,
        policy_hash,
    )
    from harness_run_manifest import build_manifest, validate_manifest
    from review_failure_candidate import main as review_failure_candidate_main
    import harness_p0_gate
except ModuleNotFoundError:
    import yaml  # type: ignore[no-redef]

    from scripts.build_harness_artifact_index import (  # type: ignore[no-redef]
        DEFAULT_REQUIRED_PATTERNS as ARTIFACT_INDEX_REQUIRED_PATTERNS,
    )
    from scripts.harness_ci_summary import (  # type: ignore[no-redef]
        build_summary as build_ci_summary,
        render_markdown as render_ci_summary,
    )
    from scripts.harness_failure_candidate import (  # type: ignore[no-redef]
        build_ci_stage_summary,
        build_failure_candidate,
        generate_candidates_from_summary,
        write_candidate,
    )
    from scripts.check_chinese_governance import build_report as build_chinese_report
    from scripts.check_evidence_index import check_evidence_index
    from scripts.check_project_development_register import parse_register
    from scripts.harness_policy import (  # type: ignore[no-redef]
        check_operation,
        load_policy,
        policy_hash,
    )
    from scripts.harness_run_manifest import build_manifest, validate_manifest  # type: ignore[no-redef]
    from scripts.review_failure_candidate import main as review_failure_candidate_main  # type: ignore[no-redef]
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


def evaluate_shallow_clone_history_contract(root_dir: Path) -> dict[str, Any]:
    root_dir = root_dir.parent if root_dir.name == "backend" else root_dir
    workflow = (root_dir / ".github" / "workflows" / "harness-p1-p2.yml").read_text(
        encoding="utf-8"
    )
    return (
        _passed("shallow_clone_history_contract")
        if "fetch-depth: 0" in workflow
        else _failed("shallow_clone_history_contract", "CI 未获取完整 Git 历史")
    )


def evaluate_ci_corpus_contract(root_dir: Path) -> dict[str, Any]:
    root_dir = root_dir.parent if root_dir.name == "backend" else root_dir
    dataset = (
        root_dir
        / "docs"
        / "harness-engineering"
        / "evals"
        / "harness-eval-dataset.json"
    )
    workflow = (root_dir / ".github" / "workflows" / "harness-p1-p2.yml").read_text(
        encoding="utf-8"
    )
    return (
        _passed("ci_corpus_contract")
        if dataset.exists() and "harness_eval_regression.py" in workflow
        else _failed("ci_corpus_contract", "CI 未显式引用本地 Harness 语料库")
    )


def evaluate_state_snapshot_parent_contract(root_dir: Path) -> dict[str, Any]:
    root_dir = root_dir.parent if root_dir.name == "backend" else root_dir
    state = (root_dir / "PROJECT-STATE.md").read_text(encoding="utf-8")
    try:
        commit = next(
            line.split("`", 2)[1]
            for line in state.splitlines()
            if "as_of_commit:" in line and "`" in line
        )
        subprocess.run(
            ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
            cwd=root_dir,
            check=True,
            capture_output=True,
        )
    except (StopIteration, subprocess.SubprocessError):
        return _failed("state_snapshot_parent_contract", "状态快照父提交不可解析")
    return _passed("state_snapshot_parent_contract")


def evaluate_artifact_failure_visibility_contract(root_dir: Path) -> dict[str, Any]:
    root_dir = root_dir.parent if root_dir.name == "backend" else root_dir
    workflow = (root_dir / ".github" / "workflows" / "harness-p1-p2.yml").read_text(
        encoding="utf-8"
    )
    passed = (
        "harness_ci_summary.py" in workflow
        and "continue-on-error: true" in workflow
        and "if: always()" in workflow
    )
    return (
        _passed("artifact_failure_visibility_contract")
        if passed
        else _failed(
            "artifact_failure_visibility_contract",
            "CI 未同时保留 artifact 与失败可见性汇总",
        )
    )


def evaluate_workflow_yaml_parseable(root_dir: Path) -> dict[str, Any]:
    root_dir = root_dir.parent if root_dir.name == "backend" else root_dir
    for relative in (
        ".github/workflows/harness-p1-p2.yml",
        ".github/workflows/harness-p0.yml",
    ):
        payload = yaml.safe_load((root_dir / relative).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "jobs" not in payload:
            return _failed("workflow_yaml_parseable", f"{relative} 无法解析或缺少 jobs")
    return _passed("workflow_yaml_parseable", "workflows=2")


def evaluate_artifact_index_coverage(root_dir: Path) -> dict[str, Any]:
    root_dir = root_dir.parent if root_dir.name == "backend" else root_dir
    workflow = (root_dir / ".github" / "workflows" / "harness-p1-p2.yml").read_text(
        encoding="utf-8"
    )
    if "build_harness_artifact_index.py" not in workflow:
        return _failed("artifact_index_coverage", "CI 未生成 artifact index")
    if "ci-quality-loop*.run.json" not in ARTIFACT_INDEX_REQUIRED_PATTERNS:
        return _failed(
            "artifact_index_coverage", "artifact index 必需集合未覆盖 .run.json"
        )
    return _passed(
        "artifact_index_coverage", "run_manifest_pattern=ci-quality-loop*.run.json"
    )


def _candidate_temp_root(directory: str) -> tuple[Path, Path, Path]:
    root = Path(directory) / "repo"
    (root / "backend").mkdir(parents=True, exist_ok=True)
    (root / "backend" / "VERSION").write_text("eval\n", encoding="utf-8")
    ledger = root / "ERRORS.md"
    ledger.write_text("暂无正式条目\n", encoding="utf-8")
    candidate_dir = root / "backend" / "reports" / "harness" / "failure-candidates"
    return root, ledger, candidate_dir


def evaluate_candidate_ledger_isolation(root_dir: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix=".tmp-harness-eval-candidate-", dir=ROOT_DIR.parent
    ) as directory:
        root, ledger, candidate_dir = _candidate_temp_root(directory)
        before = ledger.read_text(encoding="utf-8")
        report = generate_candidates_from_summary(
            build_ci_stage_summary(
                eval_report=None,
                observation_report=None,
                doc_garden_report=None,
                step_outcomes={"contract_tests": "failure"},
                run_manifest=None,
            ),
            run_id="eval-candidate",
            trace_id="20260905-harness-evidence-error-loop",
            task_id="T-HARNESS-ERROR-CANDIDATE-LOOP",
            commit_sha="a" * 40,
            candidate_dir=candidate_dir,
            root_dir=root,
            ledger_path=ledger,
        )
        if report["status"] != "generated" or not report["candidates"]:
            return _failed("candidate_ledger_isolation", "失败汇总未生成 pending 候选")
        if ledger.read_text(encoding="utf-8") != before:
            return _failed("candidate_ledger_isolation", "候选生成修改了 ERRORS.md")
    return _passed("candidate_ledger_isolation", "候选生成不触碰 ERRORS.md")


def _write_review_candidate(
    root: Path, candidate_dir: Path, name: str = "eval-candidate"
) -> Path:
    candidate = build_failure_candidate(
        source="eval",
        failure_class="verification_failure",
        summary="自评用错误候选",
        run_id="eval-review",
        trace_id="20260905-harness-evidence-error-loop",
        task_id="T-HARNESS-ERROR-CANDIDATE-LOOP",
        commit_sha="a" * 40,
        evidence_files=["backend/reports/harness/harness-eval-latest.json"],
        suggested_guardrail="人工确认后入账",
        root_dir=root,
    )
    path = candidate_dir / f"{name}.json"
    write_candidate(path, candidate)
    return path


def evaluate_review_accept_updates_ledger(root_dir: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix=".tmp-harness-eval-accept-", dir=ROOT_DIR.parent
    ) as directory:
        root, ledger, candidate_dir = _candidate_temp_root(directory)
        before = ledger.read_text(encoding="utf-8")
        candidate_path = _write_review_candidate(root, candidate_dir)
        exit_code = review_failure_candidate_main(
            [
                "--candidate",
                str(candidate_path),
                "--decision",
                "accept",
                "--operator",
                "Harness 自评",
                "--reason",
                "自评验证 accept 入账链路",
                "--root-dir",
                str(root),
                "--ledger",
                str(ledger),
                "--root-cause",
                "自评注入根因",
                "--impact",
                "自评注入影响",
                "--fix",
                "自评注入修复",
                "--new-guardrail",
                "自评注入防线",
                "--verification",
                "自评注入验证",
                "--next-time-signal",
                "自评注入信号",
            ]
        )
        after = ledger.read_text(encoding="utf-8")
        if exit_code != 0:
            return _failed("review_accept_updates_ledger", "accept 命令未成功")
        if after == before or "## M-" not in after:
            return _failed("review_accept_updates_ledger", "accept 未写入正式账本条目")
    return _passed("review_accept_updates_ledger", "accept 后 ERRORS.md 出现 M- 条目")


def evaluate_review_reject_defer_preserve_ledger(root_dir: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix=".tmp-harness-eval-reject-", dir=ROOT_DIR.parent
    ) as directory:
        for decision in ("reject", "defer"):
            root, ledger, candidate_dir = _candidate_temp_root(directory)
            before = ledger.read_text(encoding="utf-8")
            candidate_path = _write_review_candidate(
                root, candidate_dir, f"eval-candidate-{decision}"
            )
            exit_code = review_failure_candidate_main(
                [
                    "--candidate",
                    str(candidate_path),
                    "--decision",
                    decision,
                    "--operator",
                    "Harness 自评",
                    "--reason",
                    f"自评验证 {decision} 不入账",
                    "--root-dir",
                    str(root),
                    "--ledger",
                    str(ledger),
                ]
            )
            if exit_code != 0:
                return _failed(
                    "review_reject_defer_preserve_ledger", f"{decision} 命令未成功"
                )
            if ledger.read_text(encoding="utf-8") != before:
                return _failed(
                    "review_reject_defer_preserve_ledger",
                    f"{decision} 修改了 ERRORS.md",
                )
    return _passed(
        "review_reject_defer_preserve_ledger", "reject/defer 不修改 ERRORS.md"
    )


def evaluate_chinese_summary_contract(root_dir: Path) -> dict[str, Any]:
    del root_dir
    summary = build_ci_summary(
        None,
        None,
        None,
        {"contract_tests": "failure"},
        None,
        None,
    )
    markdown = render_ci_summary(summary)
    missing = [
        marker
        for marker in ("失败分类", "证据路径", "未验证范围")
        if marker not in markdown
    ]
    if missing:
        return _failed(
            "chinese_summary_contract", f"中文 Summary 缺少区段: {', '.join(missing)}"
        )
    return _passed("chinese_summary_contract", "失败分类/证据路径/未验证范围齐备")


EVALUATORS: dict[str, Callable[[Path], dict[str, Any]]] = {
    "status_label_contract": evaluate_status_label_contract,
    "policy_boundary": evaluate_policy_boundary,
    "manifest_replay_contract": evaluate_manifest_replay_contract,
    "evidence_index_integrity": evaluate_evidence_index_integrity,
    "chinese_governance_coverage": evaluate_chinese_governance_coverage,
    "p0_gate_contract": evaluate_p0_gate_contract,
    "recovery_point_contract": evaluate_recovery_point_contract,
    "policy_hash_stability": evaluate_policy_hash_stability,
    "shallow_clone_history_contract": evaluate_shallow_clone_history_contract,
    "ci_corpus_contract": evaluate_ci_corpus_contract,
    "state_snapshot_parent_contract": evaluate_state_snapshot_parent_contract,
    "artifact_failure_visibility_contract": evaluate_artifact_failure_visibility_contract,
    "workflow_yaml_parseable": evaluate_workflow_yaml_parseable,
    "artifact_index_coverage": evaluate_artifact_index_coverage,
    "candidate_ledger_isolation": evaluate_candidate_ledger_isolation,
    "review_accept_updates_ledger": evaluate_review_accept_updates_ledger,
    "review_reject_defer_preserve_ledger": evaluate_review_reject_defer_preserve_ledger,
    "chinese_summary_contract": evaluate_chinese_summary_contract,
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
