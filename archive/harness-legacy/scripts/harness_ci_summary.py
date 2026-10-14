"""汇总 P1/P2 CI 结果，并把失败显式写入 GitHub Summary。

缺失报告、步骤失败、运行 manifest 缺失和 artifact index 失败都计入 failures，
保证 CI 最终失败可见；summary 同时支持双写（GITHUB_STEP_SUMMARY + 证据文件）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# 汇总涉及的证据路径（与 workflow 步骤保持一致），用于中文 Summary 的证据路径区。
EVIDENCE_PATHS = (
    "backend/reports/harness/harness-eval-latest.json",
    "backend/reports/harness/harness-observation-latest.json",
    "backend/reports/harness/doc-garden-latest.json",
    "backend/reports/harness/ci-quality-loop.run.json",
)

FAILURE_LABELS = {
    "report_missing": "报告缺失",
    "step_failed": "步骤执行失败",
    "report_failed": "报告结论为失败",
    "index_failed": "artifact 索引缺失必需证据",
}


def _load_report(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else None


def _report_check(report: dict[str, Any] | None) -> bool:
    return bool(report and report.get("status") == "passed")


def _failure_class(
    name: str,
    payload: dict[str, Any] | None,
    outcomes: dict[str, str],
) -> str:
    """为失败项生成稳定的失败分类标记。"""
    if name in outcomes and outcomes[name] != "success":
        return "step_failed"
    if payload is None:
        return "report_missing"
    if payload.get("status") != "passed":
        return "index_failed" if name == "artifact_index" else "report_failed"
    return "unknown"


def build_summary(
    eval_report: dict[str, Any] | None,
    observation_report: dict[str, Any] | None,
    doc_garden_report: dict[str, Any] | None,
    step_outcomes: dict[str, str] | None = None,
    run_manifest: dict[str, Any] | None = None,
    artifact_index: dict[str, Any] | None = None,
    candidates_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checks = {
        "harness_eval": _report_check(eval_report),
        "harness_observation": _report_check(observation_report),
        "doc_garden": _report_check(doc_garden_report),
        "run_manifest": bool(
            run_manifest
            and run_manifest.get("run_id")
            and run_manifest.get("manifest_type") == "harness_run"
        ),
        "artifact_index": bool(
            artifact_index and artifact_index.get("status") == "passed"
        ),
    }
    outcomes = step_outcomes or {}
    for name, outcome in outcomes.items():
        if outcome and outcome != "success":
            checks[name] = False
    failures = [name for name, passed in checks.items() if not passed]
    payloads = {
        "harness_eval": eval_report,
        "harness_observation": observation_report,
        "doc_garden": doc_garden_report,
        "run_manifest": run_manifest,
        "artifact_index": artifact_index,
    }
    failure_classes = {
        name: _failure_class(name, payloads.get(name), outcomes) for name in failures
    }
    return {
        "status": "passed" if not failures else "failed",
        "checks": checks,
        "failures": failures,
        "failure_classes": failure_classes,
        "artifact_index_run_id": (
            str(artifact_index.get("run_id")) if artifact_index else ""
        ),
        "candidates": candidates_report,
        "reports": payloads,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = ["## Harness P1/P2 质量汇总", "", f"状态：**{summary['status']}**", ""]
    for name, passed in summary["checks"].items():
        lines.append(f"- {'通过' if passed else '失败'}：`{name}`")
    if summary["failures"]:
        lines.extend(["", "### 失败项", ""])
        for name in summary["failures"]:
            failure_class = summary["failure_classes"].get(name, "unknown")
            lines.append(
                f"- `{name}`：{FAILURE_LABELS.get(failure_class, failure_class)}"
                f"（failure_class={failure_class}）"
            )
    lines.extend(
        [
            "",
            "### 失败分类",
            "",
        ]
    )
    if summary["failure_classes"]:
        for name, failure_class in summary["failure_classes"].items():
            lines.append(f"- {name}={failure_class}")
    else:
        lines.append("- none（全部检查通过）")
    lines.extend(["", "### 证据路径", ""])
    for evidence_path in EVIDENCE_PATHS:
        lines.append(f"- `{evidence_path}`")
    if summary["artifact_index_run_id"]:
        lines.append(f"- artifact index run_id: `{summary['artifact_index_run_id']}`")
    lines.extend(["", "### 未验证范围", ""])
    if summary["failures"]:
        for name in summary["failures"]:
            lines.append(f"- `{name}` 失败，对应验证范围未验证，需人工复核候选与证据")
    else:
        lines.append("- 无（全部检查通过）")
    candidates = summary.get("candidates")
    if isinstance(candidates, dict):
        lines.extend(["", "### 错误候选", ""])
        lines.append(
            f"- 候选生成状态：{candidates.get('status', 'unknown')}"
            f"（生成 {len(candidates.get('candidates', []) or [])} 条，"
            f"重复 {len(candidates.get('duplicates', []) or [])} 条）"
        )
        for duplicate in candidates.get("duplicates", []) or []:
            lines.append(
                f"- 重复：`{duplicate.get('check')}` 与已有候选重复"
                f"（duplicate_of={duplicate.get('duplicate_of')}）"
            )
        for candidate in candidates.get("candidates", []) or []:
            lines.append(
                f"- 新候选：`{candidate.get('check')}`"
                f"（candidate_id={candidate.get('candidate_id')}，status=pending）"
            )
        lines.append("- 候选不会自动写入 `ERRORS.md`，需人工 review 确认后入账")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="汇总 Harness P1/P2 CI 结果")
    parser.add_argument("--eval-report", type=Path)
    parser.add_argument("--observation-report", type=Path)
    parser.add_argument("--doc-garden-report", type=Path)
    parser.add_argument("--run-manifest", type=Path)
    parser.add_argument("--artifact-index", type=Path)
    parser.add_argument("--candidates-report", type=Path)
    parser.add_argument("--outcome", action="append", default=[])
    parser.add_argument(
        "--summary-output", type=Path, help="汇总 Markdown 证据输出路径"
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    outcomes = dict(item.split("=", 1) for item in args.outcome if "=" in item)
    summary = build_summary(
        _load_report(args.eval_report),
        _load_report(args.observation_report),
        _load_report(args.doc_garden_report),
        outcomes,
        _load_report(args.run_manifest),
        _load_report(args.artifact_index),
        _load_report(args.candidates_report),
    )
    markdown = render_markdown(summary)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        Path(summary_path).write_text(markdown, encoding="utf-8")
    if args.summary_output is not None:
        if args.summary_output.exists():
            raise FileExistsError(f"拒绝覆盖已有汇总证据: {args.summary_output}")
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(markdown, encoding="utf-8")
    for failure in summary["failures"]:
        print(f"::error title=Harness P1/P2 failed::{failure}")
    print(markdown, end="")
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
