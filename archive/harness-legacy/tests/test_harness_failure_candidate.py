"""Harness 错误候选数据模型与 fingerprint 合同测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.harness_failure_candidate import (
    build_ci_stage_summary,
    build_failure_candidate,
    compute_failure_fingerprint,
    discover_duplicate,
    generate_candidates_from_summary,
    normalize_files,
    validate_candidate,
    write_candidate,
)

COMMIT = "d0af4dfd5a6ce98cf3903cae1516793ed2a96d4c"


def _build(**overrides: object) -> dict:
    kwargs: dict = {
        "source": "ci",
        "failure_class": "verification_failure",
        "summary": "P1/P2 汇总失败：doc_garden 报告缺失",
        "run_id": "ci-123",
        "trace_id": "20260905-harness-evidence-error-loop",
        "task_id": "T-HARNESS-ERROR-CANDIDATE-LOOP",
        "commit_sha": COMMIT,
        "evidence_files": ["backend/reports/harness/doc-garden-latest.json"],
        "suggested_guardrail": "补齐结构化失败报告后再允许汇总通过",
        "root_dir": Path("."),
    }
    kwargs.update(overrides)
    return build_failure_candidate(**kwargs)


def test_candidate_defaults_to_pending_and_repeatable_fingerprint() -> None:
    first = _build()
    second = _build()

    assert first["status"] == "pending"
    assert first["schema_version"] == "1.0"
    assert first["root_cause"] == ""
    assert first["impact"] == ""
    assert first["duplicate_of"] is None
    assert first["review"] == {
        "operator": None,
        "reviewed_at": None,
        "decision": None,
        "reason": None,
    }
    # 候选 ID 随机生成，但 fingerprint 必须可重复。
    assert first["candidate_id"] != second["candidate_id"]
    assert first["fingerprint"] == second["fingerprint"]


def test_fingerprint_ignores_time_ids_and_path_style() -> None:
    base = compute_failure_fingerprint(
        failure_class="verification_failure",
        summary="汇总失败  报告缺失",
        normalized_files=["backend/reports/a.json"],
    )
    # 时间戳、随机 ID、绝对路径和路径分隔符风格不得影响指纹。
    assert base == compute_failure_fingerprint(
        failure_class="verification_failure",
        summary="汇总失败 报告缺失",
        normalized_files=["backend\\reports\\a.json"],
    )
    assert base != compute_failure_fingerprint(
        failure_class="step_failed",
        summary="汇总失败 报告缺失",
        normalized_files=["backend/reports/a.json"],
    )
    assert base != compute_failure_fingerprint(
        failure_class="verification_failure",
        summary="其他失败",
        normalized_files=["backend/reports/a.json"],
    )
    assert len(base) == 64


def test_normalize_files_deduplicates_and_sorts() -> None:
    assert normalize_files(["b.json", "a.json", "b.json", ""]) == [
        "a.json",
        "b.json",
    ]


def test_validate_candidate_rejects_missing_field_bad_status_and_sha() -> None:
    candidate = _build()
    assert validate_candidate(candidate) == []

    missing = dict(candidate)
    missing.pop("fingerprint")
    issues = validate_candidate(missing)
    assert any("缺少字段 fingerprint" in issue for issue in issues)

    bad_status = dict(candidate)
    bad_status["status"] = "auto_accepted"
    assert any("非法 status" in issue for issue in validate_candidate(bad_status))

    bad_sha = dict(candidate)
    bad_sha["as_of_commit"] = "shortsha"
    assert any("as_of_commit" in issue for issue in validate_candidate(bad_sha))

    tampered = dict(candidate)
    tampered["fingerprint"] = "0" * 64
    assert any("fingerprint" in issue for issue in validate_candidate(tampered))

    reviewed_pending = dict(candidate)
    reviewed_pending["review"] = {
        "operator": "人工",
        "reviewed_at": "2026-09-05T00:00:00Z",
        "decision": "accept",
        "reason": "测试",
    }
    assert any("pending" in issue for issue in validate_candidate(reviewed_pending))


def test_build_failure_candidate_requires_valid_inputs() -> None:
    with pytest.raises(ValueError):
        _build(commit_sha="badsha")
    with pytest.raises(ValueError):
        _build(failure_class="none")
    with pytest.raises(ValueError):
        _build(summary="  ")
    with pytest.raises(ValueError):
        _build(suggested_guardrail="")


def test_discover_duplicate_checks_candidates_and_ledger(tmp_path: Path) -> None:
    candidate_dir = tmp_path / "failure-candidates"
    existing = _build()
    write_candidate(candidate_dir / "existing.json", existing)

    duplicate = _build()
    assert (
        discover_duplicate(
            duplicate, candidate_dir=candidate_dir, ledger_path=tmp_path / "ERRORS.md"
        )
        == existing["candidate_id"]
    )

    # ERRORS.md 中存在相同 fingerprint 的正式条目时也必须报重复。
    ledger = tmp_path / "ERRORS.md"
    ledger.write_text(
        f"## M-20260905-001：示例\n\n- status: guarded\n- fingerprint: {existing['fingerprint']}\n",
        encoding="utf-8",
    )
    fresh_dir = tmp_path / "other-candidates"
    assert (
        discover_duplicate(duplicate, candidate_dir=fresh_dir, ledger_path=ledger)
        == "ERRORS.md"
    )

    unrelated = _build(summary="另一类失败")
    assert (
        discover_duplicate(unrelated, candidate_dir=candidate_dir, ledger_path=ledger)
        is None
    )


def test_candidate_generation_never_modifies_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "ERRORS.md"
    ledger.write_text("暂无正式条目\n", encoding="utf-8")
    before = ledger.read_text(encoding="utf-8")

    candidate = _build()
    candidate_dir = tmp_path / "failure-candidates"
    write_candidate(candidate_dir / "candidate.json", candidate)
    discover_duplicate(candidate, candidate_dir=candidate_dir, ledger_path=ledger)

    assert ledger.read_text(encoding="utf-8") == before


def test_cli_parser_has_no_conflicting_options() -> None:
    from scripts.harness_failure_candidate import build_parser

    args = build_parser().parse_args(
        [
            "--failure-class",
            "verification_failure",
            "--summary",
            "文本摘要",
            "--suggested-guardrail",
            "防线",
            "--print-summary",
        ]
    )
    assert args.summary == "文本摘要"
    assert args.print_summary is True


def test_write_candidate_refuses_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "candidate.json"
    first = _build()
    write_candidate(target, first)
    original = target.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_candidate(target, _build(summary="另一个候选"))

    assert target.read_text(encoding="utf-8") == original
    assert json.loads(original)["candidate_id"] == first["candidate_id"]


def _failed_stage_summary() -> dict:
    return {
        "status": "failed",
        "checks": {"doc_garden": False},
        "failures": ["doc_garden"],
        "failure_classes": {"doc_garden": "report_missing"},
        "reports": {},
    }


def test_generate_candidates_from_failed_summary(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "backend").mkdir(parents=True)
    (root / "backend" / "VERSION").write_text("0.133.0-p2trial.3\n", encoding="utf-8")
    candidate_dir = tmp_path / "failure-candidates"

    report = generate_candidates_from_summary(
        _failed_stage_summary(),
        run_id="ci-42",
        trace_id="20260905-harness-evidence-error-loop",
        task_id="T-HARNESS-ERROR-CANDIDATE-LOOP",
        commit_sha=COMMIT,
        candidate_dir=candidate_dir,
        root_dir=root,
    )

    assert report["status"] == "generated"
    assert len(report["candidates"]) == 1
    written = list(candidate_dir.glob("ci-42-*.json"))
    assert len(written) == 1
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["status"] == "pending"
    assert payload["failure_class"] == "report_missing"
    assert (candidate_dir / "candidates-ci-42.json").exists()


def test_generate_candidates_from_successful_summary_writes_none_marker(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    (root / "backend").mkdir(parents=True)
    (root / "backend" / "VERSION").write_text("0.133.0-p2trial.3\n", encoding="utf-8")
    candidate_dir = tmp_path / "failure-candidates"
    stage = build_ci_stage_summary(
        eval_report={"status": "passed"},
        observation_report={"status": "passed"},
        doc_garden_report={"status": "passed"},
        step_outcomes={"contract_tests": "success"},
        run_manifest={"run_id": "run-1", "manifest_type": "harness_run"},
    )

    report = generate_candidates_from_summary(
        stage,
        run_id="ci-43",
        trace_id="trace",
        task_id="task",
        commit_sha=COMMIT,
        candidate_dir=candidate_dir,
        root_dir=root,
    )

    # CI 成功且无失败分类：不生成错误候选，只写结构化空报告。
    assert report["status"] == "none"
    assert report["candidates"] == []
    assert list(candidate_dir.glob("ci-43-*.json")) == []
    assert (candidate_dir / "candidates-ci-43.json").exists()


def test_same_fingerprint_generates_single_pending_candidate(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "backend").mkdir(parents=True)
    (root / "backend" / "VERSION").write_text("0.133.0-p2trial.3\n", encoding="utf-8")
    candidate_dir = tmp_path / "failure-candidates"
    ledger = tmp_path / "ERRORS.md"
    ledger.write_text("暂无正式条目\n", encoding="utf-8")
    kwargs: dict = {
        "run_id": "ci-44",
        "trace_id": "trace",
        "task_id": "task",
        "commit_sha": COMMIT,
        "candidate_dir": candidate_dir,
        "root_dir": root,
        "ledger_path": ledger,
    }

    first = generate_candidates_from_summary(_failed_stage_summary(), **kwargs)
    second = generate_candidates_from_summary(
        _failed_stage_summary(),
        run_id="ci-45",
        **{key: value for key, value in kwargs.items() if key != "run_id"},
    )

    assert first["status"] == "generated"
    assert second["status"] == "duplicates_only"
    assert (
        second["duplicates"][0]["duplicate_of"]
        == first["candidates"][0]["candidate_id"]
    )
    pending = [
        path for path in candidate_dir.glob("*.json") if "candidates-" not in path.name
    ]
    assert len(pending) == 1


def test_stage_summary_excludes_artifact_index_check() -> None:
    stage = build_ci_stage_summary(
        eval_report={"status": "passed"},
        observation_report={"status": "passed"},
        doc_garden_report={"status": "passed"},
        step_outcomes={"contract_tests": "success"},
        run_manifest={"run_id": "run-1", "manifest_type": "harness_run"},
    )

    # artifact index 在候选生成时尚未产生，不得计入失败来源。
    assert "artifact_index" not in stage["checks"]
    assert stage["status"] == "passed"
