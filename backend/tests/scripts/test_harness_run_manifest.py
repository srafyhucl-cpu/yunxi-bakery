"""Harness 运行 manifest 与 episode 合同测试。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import harness_run_manifest


def build_active_manifest() -> dict[str, object]:
    return harness_run_manifest.build_manifest(
        task_id="T-HARNESS-RUN-MANIFEST",
        trace_id="20260831-p0-manifest-test",
        goal="验证统一运行契约",
        model_id="test-model",
        allowed_paths=["backend/scripts/**"],
        changed_files=["backend/scripts/harness_run_manifest.py"],
        verification=["python -B -m pytest"],
        evidence=["定向合同测试"],
        plan_summary="构建并校验最小 episode",
        tool_call_count=2,
        recovery_point="继续执行策略检查",
    )


def test_active_manifest_contains_policy_and_episode() -> None:
    manifest = build_active_manifest()

    assert manifest["manifest_type"] == "harness_run"
    assert manifest["status_label"] == "进行中（active）"
    assert len(str(manifest["as_of_commit"])) == 40
    assert len(str(manifest["tool_policy_hash"])) == 64
    assert manifest["episode"]["tool_call_count"] == 2
    assert harness_run_manifest.validate_manifest(manifest) == []


def test_completed_manifest_requires_four_positive_assertions() -> None:
    with pytest.raises(ValueError, match="四项断言"):
        harness_run_manifest.build_manifest(
            task_id="T-HARNESS-RUN-MANIFEST",
            trace_id="20260831-p0-manifest-test",
            goal="拒绝不完整完成态",
            status="completed",
            result_correct=True,
            policy_compliant=True,
            evidence_complete=True,
            replayable=False,
        )


def test_manifest_validation_detects_policy_hash_tampering() -> None:
    manifest = build_active_manifest()
    tampered = copy.deepcopy(manifest)
    tampered["tool_policy_hash"] = "0" * 64

    issues = harness_run_manifest.validate_manifest(tampered)

    assert any("policy_snapshot.sha256" in issue for issue in issues)


def test_manifest_validation_executes_schema_constraints() -> None:
    manifest = build_active_manifest()
    manifest["goal"] = ""

    issues = harness_run_manifest.validate_manifest(manifest)

    assert any("goal" in issue and "minLength" in issue for issue in issues)


def test_write_artifact_refuses_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "run.run.json"
    path.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        harness_run_manifest.write_artifact(path, "{}")


def test_manifest_json_round_trip(tmp_path: Path) -> None:
    manifest = build_active_manifest()
    path = tmp_path / "run.run.json"
    harness_run_manifest.write_artifact(
        path,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )

    loaded = json.loads(path.read_text(encoding="utf-8"))

    assert harness_run_manifest.validate_manifest(loaded) == []
