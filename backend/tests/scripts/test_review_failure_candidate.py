"""错误候选人工 review 与正式入账合同测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_mistake_ledger import check_ledger
from scripts.harness_failure_candidate import (
    build_failure_candidate,
    write_candidate,
)
from scripts.review_failure_candidate import main, next_entry_id

COMMIT = "d0af4dfd5a6ce98cf3903cae1516793ed2a96d4c"
LEDGER_CONTENT = "# 错误账本\n\n## 当前条目\n\n暂无正式条目。\n"
ACCEPT_FIELDS = {
    "root_cause": "汇总步骤缺失结构化失败报告检查",
    "impact": "CI 失败被掩盖，证据包不完整",
    "fix": "汇总脚本纳入 manifest 与 artifact index 检查",
    "new_guardrail": "workflow 合同测试 + artifact index 必需文件校验",
    "verification": "定向 pytest 通过；P0 门禁通过",
    "next_time_signal": "汇总再次缺少 run_manifest 或 artifact_index 检查时阻断",
}


@pytest.fixture
def review_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    root = tmp_path / "repo"
    candidate_dir = root / "backend" / "reports" / "harness" / "failure-candidates"
    ledger = root / "ERRORS.md"
    (root / "backend").mkdir(parents=True)
    (root / "backend" / "VERSION").write_text("0.133.0-p2trial.3\n", encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    ledger.write_text(LEDGER_CONTENT, encoding="utf-8")
    candidate = build_failure_candidate(
        source="ci",
        failure_class="verification_failure",
        summary="P1/P2 汇总失败：artifact index 缺少必需证据",
        run_id="ci-42",
        trace_id="20260905-harness-evidence-error-loop",
        task_id="T-HARNESS-ERROR-CANDIDATE-LOOP",
        commit_sha=COMMIT,
        evidence_files=["backend/reports/harness/artifact-index-ci-42.json"],
        suggested_guardrail="汇总必须校验 artifact index",
        root_dir=root,
    )
    candidate_path = candidate_dir / "candidate.json"
    write_candidate(candidate_path, candidate)
    monkeypatch.setattr(
        "scripts.review_failure_candidate.ROOT_DIR", root, raising=False
    )
    return {
        "root": root,
        "candidate_dir": candidate_dir,
        "candidate_path": candidate_path,
        "candidate": candidate,
        "ledger": ledger,
    }


def _run(env: dict, decision: str, *extra: str) -> int:
    return main(
        [
            "--candidate",
            str(env["candidate_path"]),
            "--decision",
            decision,
            "--operator",
            "项目负责人",
            "--reason",
            "测试确认理由",
            "--root-dir",
            str(env["root"]),
            "--ledger",
            str(env["ledger"]),
            "--print-summary",
            *extra,
        ]
    )


def test_reject_and_defer_do_not_modify_ledger(review_env: dict) -> None:
    for decision in ("reject", "defer"):
        env = review_env
        ledger_before = env["ledger"].read_text(encoding="utf-8")
        candidate_before = env["candidate_path"].read_text(encoding="utf-8")

        exit_code = _run(env, decision)

        assert exit_code == 0
        review_files = list(env["candidate_dir"].glob("*.review.json"))
        assert len(review_files) == 1
        payload = json.loads(review_files[0].read_text(encoding="utf-8"))
        assert payload["decision"] == decision
        assert payload["operator"] == "项目负责人"
        assert payload["candidate_id"] == env["candidate"]["candidate_id"]
        assert env["ledger"].read_text(encoding="utf-8") == ledger_before
        assert env["candidate_path"].read_text(encoding="utf-8") == candidate_before
        # 清理 review 记录后用 defer 再验证一次（候选文件本身始终未被修改）。
        review_files[0].unlink()


def test_accept_writes_single_valid_ledger_entry(review_env: dict) -> None:
    env = review_env
    ledger_before = env["ledger"].read_text(encoding="utf-8")
    candidate_before = env["candidate_path"].read_text(encoding="utf-8")
    extra: list[str] = []
    for name, value in ACCEPT_FIELDS.items():
        extra += [f"--{name.replace('_', '-')}", value]

    exit_code = _run(env, "accept", *extra)

    assert exit_code == 0
    ledger_after = env["ledger"].read_text(encoding="utf-8")
    assert ledger_after != ledger_before
    assert env["candidate_path"].read_text(encoding="utf-8") == candidate_before
    # 新条目使用 M-YYYYMMDD-NNN，不复用 candidate ID 作为条目标题。
    assert f"M-{__import__('datetime').date.today():%Y%m%d}-001：" in ledger_after
    import re as re_module

    assert not re_module.search(
        rf"^##\s+{re_module.escape(str(env['candidate']['candidate_id']))}",
        ledger_after,
        re_module.MULTILINE,
    )
    result = check_ledger(env["ledger"])
    assert result.passed, result.issues
    assert any(
        entry.fields.get("fingerprint") == env["candidate"]["fingerprint"]
        for entry in result.entries
    )
    review_files = list(env["candidate_dir"].glob("*.review.json"))
    assert len(review_files) == 1
    payload = json.loads(review_files[0].read_text(encoding="utf-8"))
    assert payload["decision"] == "accept"
    assert payload["entry_id"].startswith("M-")


def test_accept_without_formal_fields_is_refused(review_env: dict) -> None:
    env = review_env
    ledger_before = env["ledger"].read_text(encoding="utf-8")

    exit_code = _run(env, "accept")

    assert exit_code == 1
    assert env["ledger"].read_text(encoding="utf-8") == ledger_before
    assert not list(env["candidate_dir"].glob("*.review.json"))


def test_accept_with_duplicate_of_requires_override(review_env: dict) -> None:
    env = review_env
    candidate = dict(env["candidate"])
    candidate["duplicate_of"] = "cand-existing000000"
    env["candidate_path"].write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    extra: list[str] = []
    for name, value in ACCEPT_FIELDS.items():
        extra += [f"--{name.replace('_', '-')}", value]

    assert _run(env, "accept", *extra) == 1
    assert env["ledger"].read_text(encoding="utf-8") == LEDGER_CONTENT

    # 显式 override 后允许入账。
    extra += ["--override-duplicate"]
    assert _run(env, "accept", *extra) == 0
    assert "M-" in env["ledger"].read_text(encoding="utf-8")


def test_entry_id_scans_existing_day_sequence() -> None:
    content = (
        "# 错误账本\n\n## M-20260905-001：旧条目\n\n- status: open\n\n"
        "## M-20260905-002：另一条\n\n- status: open\n\n"
    )
    assert next_entry_id(content, "2026-09-05") == "M-20260905-003"
    assert next_entry_id("无条目", "2026-09-05") == "M-20260905-001"
    assert next_entry_id(content, "2026-09-06") == "M-20260906-001"


def test_accept_allocates_next_id_for_same_day(review_env: dict) -> None:
    env = review_env
    env["ledger"].write_text(
        LEDGER_CONTENT.replace(
            "暂无正式条目。",
            "## M-20260905-001：当天已有条目\n\n- status: open\n- first_seen: 2026-09-05\n"
            "- severity: low\n- symptom: 旧\n- root_cause: 旧\n- impact: 旧\n- fix: 旧\n"
            "- new_guardrail: 旧\n- verification: 旧\n- linked_trace: 旧\n- linked_files: 旧\n"
            "- next_time_signal: 旧\n",
        ),
        encoding="utf-8",
    )
    extra: list[str] = ["--first-seen", "2026-09-05"]
    for name, value in ACCEPT_FIELDS.items():
        extra += [f"--{name.replace('_', '-')}", value]

    assert _run(env, "accept", *extra) == 0
    assert "M-20260905-002" in env["ledger"].read_text(encoding="utf-8")
    assert check_ledger(env["ledger"]).passed


def test_invalid_operator_is_refused(review_env: dict) -> None:
    env = review_env
    exit_code = main(
        [
            "--candidate",
            str(env["candidate_path"]),
            "--decision",
            "reject",
            "--operator",
            "   ",
            "--reason",
            "理由",
            "--root-dir",
            str(env["root"]),
            "--ledger",
            str(env["ledger"]),
            "--print-summary",
        ]
    )
    assert exit_code == 1
    assert not list(env["candidate_dir"].glob("*.review.json"))


def test_candidate_path_outside_root_is_refused(review_env: dict) -> None:
    env = review_env
    outside = env["root"].parent / "outside-candidate.json"
    outside.write_text("{}", encoding="utf-8")

    exit_code = main(
        [
            "--candidate",
            str(outside),
            "--decision",
            "reject",
            "--operator",
            "项目负责人",
            "--reason",
            "理由",
            "--root-dir",
            str(env["root"]),
            "--print-summary",
        ]
    )
    assert exit_code == 1


def test_accept_with_existing_review_file_leaves_ledger_untouched(
    review_env: dict,
) -> None:
    """审查复现场景：review 文件已存在时，accept 必须整体失败且账本不变。"""
    env = review_env
    extra: list[str] = []
    for name, value in ACCEPT_FIELDS.items():
        extra += [f"--{name.replace('_', '-')}", value]
    review_file = (
        env["candidate_dir"] / f"{env['candidate']['candidate_id']}.review.json"
    )
    review_file.write_text('{"review_type": "existing"}', encoding="utf-8")

    assert _run(env, "accept", *extra) == 1

    assert env["ledger"].read_text(encoding="utf-8") == LEDGER_CONTENT
    assert json.loads(review_file.read_text(encoding="utf-8")) == {
        "review_type": "existing"
    }


def test_commit_accept_rolls_back_review_file_on_ledger_failure(
    tmp_path: Path,
) -> None:
    from scripts.review_failure_candidate import commit_accept

    review_path = tmp_path / "cand-x.review.json"
    review_path.write_text("{}", encoding="utf-8")
    ledger_dir = tmp_path / "not-a-file"
    ledger_dir.mkdir(parents=True)

    with pytest.raises(OSError):
        commit_accept("新账本内容", ledger_path=ledger_dir, review_path=review_path)

    # 账本提交失败时，本轮新建的 review 记录被回滚，不留下半套状态。
    assert not review_path.exists()


def test_rereview_same_candidate_is_refused(review_env: dict) -> None:
    env = review_env
    assert _run(env, "reject") == 0
    assert _run(env, "defer") == 1
    assert len(list(env["candidate_dir"].glob("*.review.json"))) == 1
