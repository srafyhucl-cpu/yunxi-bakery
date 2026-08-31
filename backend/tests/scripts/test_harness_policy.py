"""Harness 策略即代码合同测试。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import check_harness_policy, harness_policy


def test_policy_hash_is_stable_and_snapshot_contains_sha256() -> None:
    policy = harness_policy.load_policy()
    first = harness_policy.policy_hash(policy)
    second = harness_policy.policy_hash(json.loads(json.dumps(policy)))

    assert first == second
    assert len(first) == harness_policy.POLICY_HASH_LENGTH
    assert harness_policy.build_policy_snapshot()["sha256"] == first


def test_forbidden_path_and_exception_are_enforced() -> None:
    policy = harness_policy.load_policy()

    assert harness_policy.check_paths(["backend/.env"], policy)
    assert harness_policy.check_paths(["backend/.env.example"], policy) == []
    assert (
        harness_policy.check_paths(
            ["backend/scripts/check_project.py"],
            policy,
            ["backend/scripts/**"],
        )
        == []
    )
    assert harness_policy.check_paths(
        ["docs/README.md"],
        policy,
        ["backend/scripts/**"],
    )


def test_high_risk_operation_requires_enablement_and_approval() -> None:
    policy = harness_policy.load_policy()

    issues = harness_policy.check_operation("production_deploy", policy)

    assert any("未启用" in issue for issue in issues)
    assert any("人工批准" in issue for issue in issues)


def test_rebuildable_cleanup_is_allowed_but_generic_recursive_delete_is_blocked() -> (
    None
):
    policy = harness_policy.load_policy()

    issues = harness_policy.check_operation("rebuildable_cleanup", policy)
    assert any("人工批准" in issue for issue in issues)
    assert (
        harness_policy.check_operation(
            "rebuildable_cleanup", policy, human_approved=True
        )
        == []
    )
    issues = harness_policy.check_operation("recursive_delete", policy)

    assert any("任意路径递归删除" in issue for issue in issues)
    assert any("未启用" in issue for issue in issues)


def test_policy_loader_rejects_invalid_document(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text("[]", encoding="utf-8")

    try:
        harness_policy.load_policy(path)
    except harness_policy.PolicyError as exc:
        assert "根节点必须是对象" in str(exc)
    else:
        raise AssertionError("非法策略文档未被拒绝")


def test_collect_changed_paths_supports_commit_range(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("one", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    tracked.write_text("two", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "head"], cwd=tmp_path, check=True)
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()

    assert check_harness_policy.collect_changed_paths(
        tmp_path, base=base, head=head
    ) == ["tracked.txt"]


def test_policy_cli_rejects_partial_commit_range() -> None:
    assert check_harness_policy.main(["--base", "a" * 40, "--summary"]) == 1


def test_policy_commit_range_rejects_unavailable_sha(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    try:
        check_harness_policy.collect_changed_paths(
            tmp_path, base="0" * 40, head="f" * 40
        )
    except check_harness_policy.PolicyError as exc:
        assert "目标提交不可用" in str(exc)
    else:
        raise AssertionError("不可用 Git 提交未被拒绝")
