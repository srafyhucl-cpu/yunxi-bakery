"""Harness 错误候选数据模型、稳定 fingerprint 与重复发现。

候选是 CI 失败自动生成的建议记录，默认状态 pending；候选生成器绝不修改
根目录 `ERRORS.md`，只有 `review_failure_candidate.py` 在人工确认后才入账。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

try:
    from harness_ci_summary import EVIDENCE_PATHS, build_summary
    from harness_run_manifest import read_version, utc_now
except ModuleNotFoundError:
    from scripts.harness_ci_summary import (  # type: ignore[no-redef]
        EVIDENCE_PATHS,
        build_summary,
    )
    from scripts.harness_run_manifest import read_version, utc_now  # type: ignore[no-redef]

ROOT_DIR = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    ROOT_DIR / "docs" / "harness-engineering" / "core" / "failure-candidate.schema.json"
)
SCHEMA_VERSION = "1.0"
CANDIDATE_TYPE = "harness_failure_candidate"
ALLOWED_STATUS = frozenset({"pending", "accepted", "rejected", "deferred"})
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")

CANDIDATE_FIELDS = (
    "schema_version",
    "candidate_id",
    "fingerprint",
    "status",
    "source",
    "created_at",
    "failure_class",
    "summary",
    "symptom",
    "root_cause",
    "impact",
    "suggested_guardrail",
    "run_id",
    "trace_id",
    "task_id",
    "as_of_commit",
    "version",
    "evidence_files",
    "duplicate_of",
    "review",
)


def normalize_summary(summary: str) -> str:
    """压缩空白，保证 fingerprint 只依赖稳定文本。"""
    return " ".join(summary.split())


def normalize_files(files: list[str]) -> list[str]:
    """规范化证据路径：正斜杠、去空、去重、排序。"""
    normalized = {
        str(item).replace("\\", "/").strip().lstrip("./")
        for item in files
        if str(item).strip()
    }
    return sorted(normalized)


def compute_failure_fingerprint(
    *,
    failure_class: str,
    summary: str,
    normalized_files: list[str],
) -> str:
    """基于稳定字段计算 SHA-256 指纹；不含时间、绝对路径或随机 ID。"""
    payload = json.dumps(
        {
            "failure_class": failure_class.strip(),
            "summary": normalize_summary(summary),
            "files": normalize_files(normalized_files),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def new_candidate_id() -> str:
    return f"cand-{uuid.uuid4().hex[:16]}"


def build_failure_candidate(
    *,
    source: str,
    failure_class: str,
    summary: str,
    run_id: str | None,
    trace_id: str | None,
    task_id: str | None,
    commit_sha: str,
    evidence_files: list[str],
    suggested_guardrail: str,
    root_dir: Path,
    duplicate_of: str | None = None,
) -> dict[str, Any]:
    """构建一个 pending 状态的错误候选；fingerprint 可重复计算。"""
    if not COMMIT_RE.fullmatch(commit_sha):
        raise ValueError(f"commit_sha 必须是 40 位小写 SHA: {commit_sha}")
    if not source.strip():
        raise ValueError("source 不能为空")
    if not failure_class.strip() or failure_class.strip() == "none":
        raise ValueError("failure_class 不能为空或 none")
    if not summary.strip():
        raise ValueError("summary 不能为空")
    if not suggested_guardrail.strip():
        raise ValueError("suggested_guardrail 不能为空")
    normalized_files = normalize_files(evidence_files)
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": new_candidate_id(),
        "fingerprint": compute_failure_fingerprint(
            failure_class=failure_class,
            summary=summary,
            normalized_files=normalized_files,
        ),
        "status": "pending",
        "source": source.strip(),
        "created_at": utc_now(),
        "failure_class": failure_class.strip(),
        "summary": normalize_summary(summary),
        "symptom": summary.strip(),
        "root_cause": "",
        "impact": "",
        "suggested_guardrail": suggested_guardrail.strip(),
        "run_id": (run_id or "").strip() or None,
        "trace_id": (trace_id or "").strip() or None,
        "task_id": (task_id or "").strip() or None,
        "as_of_commit": commit_sha,
        "version": read_version(root_dir),
        "evidence_files": normalized_files,
        "duplicate_of": duplicate_of,
        "review": {
            "operator": None,
            "reviewed_at": None,
            "decision": None,
            "reason": None,
        },
    }


def validate_candidate(candidate: dict[str, Any]) -> list[str]:
    """校验候选结构与约束，返回中文问题列表。"""
    issues: list[str] = []
    if not isinstance(candidate, dict):
        return ["候选必须是对象"]
    for field_name in CANDIDATE_FIELDS:
        if field_name not in candidate:
            issues.append(f"缺少字段 {field_name}")
    if any(issues):
        return issues
    unknown = sorted(set(candidate) - set(CANDIDATE_FIELDS))
    if unknown:
        issues.append(f"存在未定义字段: {', '.join(unknown)}")
    if candidate["schema_version"] != SCHEMA_VERSION:
        issues.append("schema_version 必须为 1.0")
    if not ID_RE.fullmatch(str(candidate["candidate_id"])):
        issues.append(f"candidate_id 格式无效: {candidate['candidate_id']}")
    if not SHA256_RE.fullmatch(str(candidate["fingerprint"])):
        issues.append("fingerprint 必须是 64 位 SHA-256")
    if candidate["status"] not in ALLOWED_STATUS:
        issues.append(f"非法 status: {candidate['status']}")
    if not COMMIT_RE.fullmatch(str(candidate["as_of_commit"])):
        issues.append("as_of_commit 必须是 40 位小写 SHA")
    if not isinstance(candidate["evidence_files"], list):
        issues.append("evidence_files 必须是数组")
    if not str(candidate["summary"]).strip():
        issues.append("summary 不能为空")
    if not str(candidate["suggested_guardrail"]).strip():
        issues.append("suggested_guardrail 不能为空")
    review = candidate.get("review")
    if not isinstance(review, dict) or set(review) != {
        "operator",
        "reviewed_at",
        "decision",
        "reason",
    }:
        issues.append("review 必须包含 operator/reviewed_at/decision/reason 四个字段")
    elif candidate["status"] == "pending" and review.get("decision") is not None:
        issues.append("pending 候选不得携带 review 决定")
    try:
        datetime.fromisoformat(str(candidate["created_at"]).replace("Z", "+00:00"))
    except ValueError:
        issues.append("created_at 必须是 RFC3339 时间戳")
    expected_fingerprint = compute_failure_fingerprint(
        failure_class=str(candidate["failure_class"]),
        summary=str(candidate["summary"]),
        normalized_files=list(candidate["evidence_files"]),
    )
    if (
        candidate["status"] == "pending"
        and candidate["fingerprint"] != expected_fingerprint
    ):
        issues.append("fingerprint 与稳定字段不一致，候选可能被篡改")
    return issues


def discover_duplicate(
    candidate: dict[str, Any],
    *,
    candidate_dir: Path,
    ledger_path: Path,
) -> str | None:
    """同时检查候选目录和 ERRORS.md，返回重复目标；没有重复返回 None。"""
    fingerprint = str(candidate.get("fingerprint") or "")
    if not fingerprint:
        raise ValueError("候选缺少 fingerprint，无法查重")
    if candidate_dir.is_dir():
        for path in sorted(candidate_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("fingerprint") != fingerprint:
                continue
            if payload.get("candidate_id") == candidate.get("candidate_id"):
                continue
            return str(payload.get("candidate_id") or path.name)
    if ledger_path.is_file():
        content = ledger_path.read_text(encoding="utf-8")
        if re.search(
            rf"^\s*-\s*fingerprint:\s*{re.escape(fingerprint)}\s*$",
            content,
            re.MULTILINE,
        ):
            return "ERRORS.md"
    return None


def write_candidate(path: Path, candidate: dict[str, Any]) -> None:
    """写出候选文件；已存在路径拒绝覆盖，候选历史不可篡改。"""
    if path.exists():
        raise FileExistsError(f"拒绝覆盖已有候选文件: {path}")
    issues = validate_candidate(candidate)
    if issues:
        raise ValueError("候选校验失败: " + "；".join(issues))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def default_candidate_dir(root_dir: Path = ROOT_DIR) -> Path:
    return root_dir / "backend" / "reports" / "harness" / "failure-candidates"


CANDIDATE_REPORT_TYPE = "harness_failure_candidate_generation"


def _safe_run_id(run_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", run_id).strip("-")
    return safe or "run"


def _collect_failure_sources(summary: dict[str, Any]) -> list[tuple[str, str]]:
    """收集候选来源：失败检查 + 报告内部明确 failed（即使步骤成功）。"""
    sources: list[tuple[str, str]] = []
    failure_classes = summary.get("failure_classes") or {}
    for name in summary.get("failures") or []:
        sources.append(
            (str(name), str(failure_classes.get(name, "verification_failure")))
        )
    for name, payload in (summary.get("reports") or {}).items():
        if not isinstance(payload, dict):
            continue
        if payload.get("status") == "failed" and str(name) not in {
            item for item, _ in sources
        }:
            sources.append((str(name), "report_failed"))
    return sources


def generate_candidates_from_summary(
    summary: dict[str, Any],
    *,
    run_id: str,
    trace_id: str | None,
    task_id: str | None,
    commit_sha: str,
    candidate_dir: Path,
    root_dir: Path,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """从 CI 汇总生成错误候选；成功且无失败分类时只写结构化空报告。

    - 同一 fingerprint 只保留一个 pending 候选，重复失败在运行报告中记录 duplicate_of。
    - 候选生成绝不修改 `ERRORS.md`。
    - 生成的候选汇总文件（candidates-<run_id>.json）同时作为 artifact index 的候选目录证据。
    """
    safe_run_id = _safe_run_id(run_id)
    sources = _collect_failure_sources(summary)
    candidates: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for name, failure_class in sources:
        candidate = build_failure_candidate(
            source="ci",
            failure_class=failure_class,
            summary=f"Harness P1/P2 检查 {name} 失败（{failure_class}）",
            run_id=run_id,
            trace_id=trace_id,
            task_id=task_id,
            commit_sha=commit_sha,
            evidence_files=list(EVIDENCE_PATHS),
            suggested_guardrail=(
                "人工确认该失败是否值得记入 ERRORS.md，并补充对应回归防线"
            ),
            root_dir=root_dir,
        )
        duplicate_of = (
            discover_duplicate(
                candidate, candidate_dir=candidate_dir, ledger_path=ledger_path
            )
            if ledger_path is not None
            else None
        )
        if duplicate_of is not None:
            duplicates.append(
                {
                    "check": name,
                    "duplicate_of": duplicate_of,
                    "fingerprint": candidate["fingerprint"],
                }
            )
            continue
        write_candidate(candidate_dir / f"{safe_run_id}-{name}.json", candidate)
        candidates.append({"check": name, "candidate_id": candidate["candidate_id"]})
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "candidate_generation_type": CANDIDATE_REPORT_TYPE,
        "generated_at": utc_now(),
        "run_id": run_id,
        "trace_id": trace_id,
        "task_id": task_id,
        "as_of_commit": commit_sha,
        "status": (
            "none"
            if not sources
            else ("generated" if candidates else "duplicates_only")
        ),
        "candidates": candidates,
        "duplicates": duplicates,
    }
    marker_path = candidate_dir / f"candidates-{safe_run_id}.json"
    if marker_path.exists():
        raise FileExistsError(f"拒绝覆盖已有候选生成报告: {marker_path}")
    candidate_dir.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report["summary_file"] = marker_path.as_posix()
    return report


def build_ci_stage_summary(
    *,
    eval_report: dict[str, Any] | None,
    observation_report: dict[str, Any] | None,
    doc_garden_report: dict[str, Any] | None,
    step_outcomes: dict[str, str] | None,
    run_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    """构建候选生成前的阶段性汇总（artifact index 尚未生成，需剔除该项）。"""
    stage = build_summary(
        eval_report,
        observation_report,
        doc_garden_report,
        step_outcomes,
        run_manifest,
        None,
    )
    stage["checks"].pop("artifact_index", None)
    stage["failures"] = [name for name in stage["failures"] if name != "artifact_index"]
    stage["failure_classes"].pop("artifact_index", None)
    stage["reports"].pop("artifact_index", None)
    stage["status"] = "passed" if not stage["failures"] else "failed"
    return stage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成或校验 Harness 错误候选")
    parser.add_argument("--source", default="ci")
    parser.add_argument("--failure-class", required=False)
    parser.add_argument("--summary")
    parser.add_argument("--run-id")
    parser.add_argument("--trace-id")
    parser.add_argument("--task-id")
    parser.add_argument("--commit-sha", default="")
    parser.add_argument("--evidence-file", action="append", default=[])
    parser.add_argument("--suggested-guardrail")
    parser.add_argument("--candidate-dir", type=Path, default=default_candidate_dir())
    parser.add_argument("--root-dir", type=Path, default=ROOT_DIR)
    parser.add_argument(
        "--ledger", type=Path, default=None, help="ERRORS.md 路径，用于查重"
    )
    parser.add_argument(
        "--output", type=Path, help="候选 JSON 输出路径；缺省按指纹命名"
    )
    parser.add_argument("--validate", type=Path, help="校验已有候选文件")
    parser.add_argument("--print-summary", dest="print_summary", action="store_true")
    parser.add_argument(
        "--from-ci",
        action="store_true",
        help="从 CI 步骤结果与报告生成候选（workflow 使用；成功时只写结构化空报告）",
    )
    parser.add_argument("--eval-report", type=Path)
    parser.add_argument("--observation-report", type=Path)
    parser.add_argument("--doc-garden-report", type=Path)
    parser.add_argument("--run-manifest", type=Path)
    parser.add_argument("--outcome", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.validate:
            payload = json.loads(args.validate.read_text(encoding="utf-8-sig"))
            issues = validate_candidate(payload if isinstance(payload, dict) else {})
            if issues:
                print("[failure-candidate] FAIL")
                for issue in issues:
                    print(f"  - {issue}")
                return 1
            print(
                f"[failure-candidate] PASS candidate_id={payload.get('candidate_id')}"
            )
            return 0
        if args.from_ci:
            if not args.run_id:
                raise ValueError("--from-ci 必须提供 --run-id")
            commit_sha = args.commit_sha
            if not commit_sha:
                try:
                    from harness_run_manifest import resolve_commit
                except ModuleNotFoundError:
                    from scripts.harness_run_manifest import resolve_commit  # type: ignore[no-redef]
                commit_sha = resolve_commit(Path(args.root_dir))
            outcomes = dict(item.split("=", 1) for item in args.outcome if "=" in item)

            def _load(path: Path | None) -> dict[str, Any] | None:
                if path is None or not path.exists():
                    return None
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                return payload if isinstance(payload, dict) else None

            stage = build_ci_stage_summary(
                eval_report=_load(args.eval_report),
                observation_report=_load(args.observation_report),
                doc_garden_report=_load(args.doc_garden_report),
                step_outcomes=outcomes,
                run_manifest=_load(args.run_manifest),
            )
            report = generate_candidates_from_summary(
                stage,
                run_id=args.run_id,
                trace_id=args.trace_id,
                task_id=args.task_id,
                commit_sha=commit_sha,
                candidate_dir=Path(args.candidate_dir),
                root_dir=Path(args.root_dir),
                ledger_path=args.ledger,
            )
            if args.print_summary:
                print(
                    f"failure_candidate_generation status={report['status']} "
                    f"generated={len(report['candidates'])} "
                    f"duplicates={len(report['duplicates'])} "
                    f"run_id={report['run_id']}"
                )
            else:
                print(
                    f"[failure-candidate] PASS generation={report['status']} "
                    f"generated={len(report['candidates'])} "
                    f"duplicates={len(report['duplicates'])}"
                )
            print(f"summary_file={report['summary_file']}")
            return 0
        if not args.failure_class or not args.summary or not args.suggested_guardrail:
            raise ValueError(
                "单候选模式必须提供 --failure-class、--summary、--suggested-guardrail"
            )
        commit_sha = args.commit_sha
        if not commit_sha:
            try:
                from harness_run_manifest import resolve_commit
            except ModuleNotFoundError:
                from scripts.harness_run_manifest import resolve_commit  # type: ignore[no-redef]
            commit_sha = resolve_commit(Path(args.root_dir))
        candidate = build_failure_candidate(
            source=args.source,
            failure_class=args.failure_class,
            summary=args.summary,
            run_id=args.run_id,
            trace_id=args.trace_id,
            task_id=args.task_id,
            commit_sha=commit_sha,
            evidence_files=args.evidence_file,
            suggested_guardrail=args.suggested_guardrail,
            root_dir=Path(args.root_dir),
        )
        if args.ledger is not None:
            candidate["duplicate_of"] = discover_duplicate(
                candidate,
                candidate_dir=Path(args.candidate_dir),
                ledger_path=Path(args.ledger),
            )
        output = args.output
        if output is None:
            output = Path(args.candidate_dir) / f"{candidate['fingerprint'][:16]}.json"
        write_candidate(output, candidate)
    except (OSError, ValueError, FileExistsError) as exc:
        print(f"[failure-candidate] FAIL {exc}", file=sys.stderr)
        return 1
    if args.print_summary:
        print(
            f"failure_candidate status={candidate['status']} "
            f"candidate_id={candidate['candidate_id']} "
            f"fingerprint={candidate['fingerprint']} "
            f"duplicate_of={candidate['duplicate_of']}"
        )
    else:
        print(f"[failure-candidate] PASS candidate_id={candidate['candidate_id']}")
    print(f"output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
