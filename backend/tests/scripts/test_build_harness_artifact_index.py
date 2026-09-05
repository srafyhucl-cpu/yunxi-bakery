"""Harness artifact 索引生成脚本合同测试。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.build_harness_artifact_index import (
    build_artifact_index,
    sha256_file,
    write_artifact_index,
)

REQUIRED_PATTERNS = (
    "harness-eval-*.json",
    "harness-observation-*.json",
    "doc-garden-*.json",
    "ci-quality-loop*.run.json",
    "artifact-index*.json",
    "failure-candidates/*.json",
)


def _write(path: Path, content: str = "{}\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_empty_dir_reports_missing_required_files(tmp_path: Path) -> None:
    payload = build_artifact_index(
        tmp_path,
        run_id="run-empty",
        required_patterns=REQUIRED_PATTERNS,
        commit_sha="a" * 40,
    )

    assert payload["status"] == "failed"
    assert payload["missing_files"] == list(REQUIRED_PATTERNS)
    assert payload["files"] == []
    assert payload["schema_version"] == "1.0"
    assert payload["artifact_index_type"] == "harness_artifact_index"
    assert payload["generated_at"]
    assert payload["commit_sha"] == "a" * 40


def test_missing_required_file_keeps_index_output(tmp_path: Path) -> None:
    _write(tmp_path / "harness-eval-20260905.json")
    payload = build_artifact_index(
        tmp_path,
        run_id="run-partial",
        required_patterns=REQUIRED_PATTERNS,
        commit_sha="b" * 40,
    )

    assert payload["status"] == "failed"
    assert "harness-eval-*.json" not in payload["missing_files"]
    assert "doc-garden-*.json" in payload["missing_files"]
    assert "failure-candidates/*.json" in payload["missing_files"]
    assert [entry["path"] for entry in payload["files"]] == [
        "harness-eval-20260905.json"
    ]


def test_full_dir_passes_and_hashes_match_actual_files(tmp_path: Path) -> None:
    eval_path = _write(tmp_path / "harness-eval-20260905.json", '{"status":"passed"}\n')
    _write(tmp_path / "harness-observation-20260905.json")
    _write(tmp_path / "doc-garden-20260905.json")
    _write(tmp_path / "ci-quality-loop-20260905.run.json")
    candidate = _write(tmp_path / "failure-candidates" / "candidate-1.json")

    payload = build_artifact_index(
        tmp_path,
        run_id="run-full",
        required_patterns=REQUIRED_PATTERNS,
        index_filename="artifact-index-run-full.json",
        commit_sha="c" * 40,
    )

    assert payload["status"] == "passed", payload["missing_files"]
    assert payload["missing_files"] == []
    entries = {entry["path"]: entry for entry in payload["files"]}
    eval_entry = entries["harness-eval-20260905.json"]
    assert eval_entry["sha256"] == hashlib.sha256(eval_path.read_bytes()).hexdigest()
    assert eval_entry["size_bytes"] == eval_path.stat().st_size
    assert eval_entry["exists"] is True
    candidate_entry = entries["failure-candidates/candidate-1.json"]
    assert candidate_entry["sha256"] == sha256_file(candidate)
    self_entry = entries["artifact-index-run-full.json"]
    assert self_entry["exists"] is True
    assert self_entry["self_reference"] is True


def test_hash_computation_is_stable_across_builds(tmp_path: Path) -> None:
    _write(tmp_path / "harness-eval-20260905.json", '{"status":"passed"}\n')
    _write(tmp_path / "failure-candidates" / "candidate-1.json")

    first = build_artifact_index(
        tmp_path,
        run_id="run-stable",
        required_patterns=("harness-eval-*.json",),
        commit_sha="d" * 40,
    )
    second = build_artifact_index(
        tmp_path,
        run_id="run-stable",
        required_patterns=("harness-eval-*.json",),
        commit_sha="d" * 40,
    )

    assert first["files"] == second["files"]


def test_write_artifact_index_refuses_overwrite(tmp_path: Path) -> None:
    payload = build_artifact_index(
        tmp_path, run_id="run-ow", required_patterns=(), commit_sha="e" * 40
    )
    target = tmp_path / "artifact-index.json"
    write_artifact_index(target, payload)
    original = target.read_text(encoding="utf-8")

    try:
        write_artifact_index(target, payload)
    except FileExistsError:
        pass
    else:
        raise AssertionError("索引写入不应覆盖已有证据文件")

    assert target.read_text(encoding="utf-8") == original
    reparsed = json.loads(original)
    assert reparsed["run_id"] == "run-ow"


def test_traversal_and_absolute_patterns_are_rejected(tmp_path: Path) -> None:
    for pattern in ("../outside.json", "..\\outside.json", "C:/evil/*.json"):
        try:
            build_artifact_index(
                tmp_path,
                run_id="run-evil",
                required_patterns=(pattern,),
                commit_sha="f" * 40,
            )
        except ValueError:
            continue
        raise AssertionError(f"模式应被拒绝: {pattern}")


def test_index_filename_satisfies_artifact_index_pattern(tmp_path: Path) -> None:
    payload = build_artifact_index(
        tmp_path,
        run_id="run-self",
        required_patterns=("artifact-index*.json",),
        index_filename="artifact-index-run-self.json",
        commit_sha="a" * 40,
    )

    assert payload["status"] == "passed"
    assert payload["missing_files"] == []
