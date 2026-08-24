from __future__ import annotations

from pathlib import Path
import hashlib
import subprocess

from scripts import check_evidence_index as evidence_check


def _valid_entry(entry_id: str = evidence_check.PREFLIGHT_CONTRACT_EVIDENCE_ID) -> str:
    checker_sha = hashlib.sha256(b"checker").hexdigest()
    report_sha = hashlib.sha256(b"report").hexdigest()
    return (
        f"## {entry_id}：预检业务合约证据复核\n\n"
        "- trace_id: 20260706-preflight-contract-evidence-check\n"
        "- generated_at: 2026-07-06\n"
        "- evidence_type: local/preflight-business-contract-evidence\n"
        "- file: `repo:scripts/check_preflight_business_contracts.py`; "
        "`repo:reports/preflight-contract-check-20260706-232901.json`\n"
        "- command: `python scripts/check_preflight_business_contracts.py "
        '"reports\\preflight-contract-check-20260706-232901.json" --summary`\n'
        "- result: pass\n"
        "- related_logbook: 2026-07-06 - chore(preflight): 新增预检业务合约证据复核脚本\n"
        "- related_adr: none\n"
        "- contains_sensitive_data: no\n"
        "- retention_note: 不记录密钥、客户数据或订单明细。\n"
        "- storage_scope: repository\n"
        f"- sha256: scripts/check_preflight_business_contracts.py={checker_sha}；"
        f"reports/preflight-contract-check-20260706-232901.json={report_sha}\n"
        "- summary: 校验 `business_contracts.static_checks` 包含四类业务合约状态。\n"
    )


def _write_referenced_files(tmp_path: Path) -> tuple[Path, Path]:
    checker_path = tmp_path / "scripts" / "check_preflight_business_contracts.py"
    report_path = tmp_path / "reports" / "preflight-contract-check-20260706-232901.json"
    checker_path.parent.mkdir()
    report_path.parent.mkdir()
    checker_path.write_text("checker", encoding="utf-8")
    report_path.write_text("report", encoding="utf-8")
    return checker_path, report_path


def test_complete_evidence_index_passes(tmp_path: Path) -> None:
    _write_referenced_files(tmp_path)
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text("# Evidence Index\n\n" + _valid_entry(), encoding="utf-8")

    result = evidence_check.check_evidence_index(evidence_file)

    assert result.passed is True
    assert len(result.entries) == 1
    assert result.entries[0].entry_id == evidence_check.PREFLIGHT_CONTRACT_EVIDENCE_ID


def test_missing_required_field_fails(tmp_path: Path) -> None:
    _write_referenced_files(tmp_path)
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text(
        "# Evidence Index\n\n" + _valid_entry().replace("- command:", "- missing:"),
        encoding="utf-8",
    )

    result = evidence_check.check_evidence_index(evidence_file)

    assert result.passed is False
    assert any("missing field `command`" in issue for issue in result.issues)


def test_missing_storage_scope_fails(tmp_path: Path) -> None:
    _write_referenced_files(tmp_path)
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text(
        "# Evidence Index\n\n"
        + _valid_entry().replace("- storage_scope: repository\n", ""),
        encoding="utf-8",
    )

    result = evidence_check.check_evidence_index(evidence_file)

    assert result.passed is False
    assert any("missing field `storage_scope`" in issue for issue in result.issues)


def test_bare_relative_path_requires_prefix_fails(tmp_path: Path) -> None:
    _write_referenced_files(tmp_path)
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text(
        "# Evidence Index\n\n" + _valid_entry().replace("repo:scripts/", "scripts/"),
        encoding="utf-8",
    )

    result = evidence_check.check_evidence_index(evidence_file)

    assert result.passed is False
    assert any("禁止裸路径" in issue for issue in result.issues)


def test_repo_artifact_without_sha256_fails(tmp_path: Path) -> None:
    _write_referenced_files(tmp_path)
    evidence_file = tmp_path / "evidence-index.md"
    entry_lines = [
        line for line in _valid_entry().splitlines() if not line.startswith("- sha256:")
    ]
    evidence_file.write_text(
        "# Evidence Index\n\n" + "\n".join(entry_lines), encoding="utf-8"
    )

    result = evidence_check.check_evidence_index(evidence_file)

    assert result.passed is False
    assert any("缺少 sha256" in issue for issue in result.issues)


def test_invalid_result_and_sensitive_flag_fail(tmp_path: Path) -> None:
    _write_referenced_files(tmp_path)
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text(
        "# Evidence Index\n\n"
        + _valid_entry()
        .replace("- result: pass", "- result: ok")
        .replace("- contains_sensitive_data: no", "- contains_sensitive_data: false"),
        encoding="utf-8",
    )

    result = evidence_check.check_evidence_index(evidence_file)

    assert result.passed is False
    assert any("invalid result" in issue for issue in result.issues)
    assert any("invalid contains_sensitive_data" in issue for issue in result.issues)


def test_retired_missing_evidence_is_explicitly_excluded(tmp_path: Path) -> None:
    evidence_file = tmp_path / "evidence-index.md"
    entry = _valid_entry().replace(
        "- result: pass",
        "- result: pass\n- evidence_status: retired\n",
    )
    evidence_file.write_text("# Evidence Index\n\n" + entry, encoding="utf-8")

    result = evidence_check.check_evidence_index(evidence_file)
    report = evidence_check.build_json_report(result, evidence_file)

    assert result.passed is True
    assert report["retired"] == 1
    assert report["verified_files"] == 0


def test_invalid_evidence_status_fails(tmp_path: Path) -> None:
    _write_referenced_files(tmp_path)
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text(
        "# Evidence Index\n\n"
        + _valid_entry().replace(
            "- result: pass",
            "- result: pass\n- evidence_status: archived",
        ),
        encoding="utf-8",
    )

    result = evidence_check.check_evidence_index(evidence_file)

    assert result.passed is False
    assert any("invalid evidence_status" in issue for issue in result.issues)


def test_preflight_contract_entry_requires_checker_and_report_refs(
    tmp_path: Path,
) -> None:
    _write_referenced_files(tmp_path)
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text(
        "# Evidence Index\n\n"
        + _valid_entry()
        .replace("scripts/check_preflight_business_contracts.py", "scripts/other.py")
        .replace(
            "reports/preflight-contract-check-20260706-232901.json",
            "reports/other.json",
        )
        .replace(
            "reports\\preflight-contract-check-20260706-232901.json",
            "reports\\other.json",
        ),
        encoding="utf-8",
    )

    result = evidence_check.check_evidence_index(evidence_file)

    assert result.passed is False
    assert any(
        "check_preflight_business_contracts.py" in issue for issue in result.issues
    )
    assert any(
        "preflight-contract-check-20260706-232901.json" in issue
        for issue in result.issues
    )


def test_duplicate_evidence_id_fails(tmp_path: Path) -> None:
    _write_referenced_files(tmp_path)
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text(
        "# Evidence Index\n\n" + _valid_entry() + "\n" + _valid_entry(),
        encoding="utf-8",
    )

    result = evidence_check.check_evidence_index(evidence_file)

    assert result.passed is False
    assert any("duplicate evidence id" in issue for issue in result.issues)


def test_main_outputs_summary_and_json(tmp_path: Path, capsys) -> None:
    checker_path, report_path = _write_referenced_files(tmp_path)
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text("# Evidence Index\n\n" + _valid_entry(), encoding="utf-8")

    summary_exit_code = evidence_check.main(["--path", str(evidence_file), "--summary"])
    summary_output = capsys.readouterr().out
    json_exit_code = evidence_check.main(["--path", str(evidence_file), "--json"])
    json_output = capsys.readouterr().out

    assert summary_exit_code == 0
    assert "evidence_index status=passed" in summary_output
    assert json_exit_code == 0
    assert '"status": "passed"' in json_output
    assert '"verified_files": 2' in json_output
    assert hashlib.sha256(checker_path.read_bytes()).hexdigest() in json_output
    assert hashlib.sha256(report_path.read_bytes()).hexdigest() in json_output


def test_missing_evidence_file_fails(tmp_path: Path) -> None:
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text("# Evidence Index\n\n" + _valid_entry(), encoding="utf-8")

    result = evidence_check.check_evidence_index(evidence_file)

    assert result.passed is False
    assert any("repo 工件缺失" in issue for issue in result.issues)


def test_local_artifact_missing_does_not_block(tmp_path: Path) -> None:
    _write_referenced_files(tmp_path)
    evidence_file = tmp_path / "evidence-index.md"
    entry = _valid_entry() + (
        "\n## E-20260814-099：本地留存工件缺失容忍\n\n"
        "- trace_id: 20260814-local-artifact-test\n"
        "- generated_at: 2026-08-14\n"
        "- evidence_type: governance/secret-scan-gate-finalize\n"
        "- file: `local:reports/harness/missing-local-artifact-20260814.json`; "
        "`repo:scripts/check_preflight_business_contracts.py`\n"
        "- command: `python -m pre_commit run detect-secrets --all-files`\n"
        "- result: pass\n"
        "- related_logbook: 2026-08-14 - docs(governance): 本地工件语义测试\n"
        "- related_adr: none\n"
        "- contains_sensitive_data: no\n"
        "- retention_note: 本地留存工件缺失不阻断新环境。\n"
        "- storage_scope: local\n"
        "- summary: 校验本地留存工件缺失时不阻断提交门禁。\n"
    )
    evidence_file.write_text("# Evidence Index\n\n" + entry, encoding="utf-8")

    result = evidence_check.check_evidence_index(evidence_file)
    report = evidence_check.build_json_report(result, evidence_file)

    assert result.passed is True
    assert any(
        item["kind"] == "local-artifact-missing" for item in report["file_integrity"]
    )
    assert not any("缺失" in issue for issue in result.issues)


def _scope_entry(
    file_ref: str,
    sha256: str | None = None,
    *,
    scope: str = "local",
) -> str:
    sha_line = f"- sha256: {sha256}\n" if sha256 else ""
    return (
        "\n## E-20260814-098：storage_scope 语义测试\n\n"
        "- trace_id: 20260814-storage-scope-test\n"
        "- generated_at: 2026-08-14\n"
        "- evidence_type: governance/storage-scope-test\n"
        f"- file: `{file_ref}`\n"
        "- command: `python scripts/check_evidence_index.py`\n"
        "- result: pass\n"
        "- related_logbook: 2026-08-14 - docs(governance): storage_scope 测试\n"
        "- related_adr: none\n"
        "- contains_sensitive_data: no\n"
        "- retention_note: 测试条目。\n"
        f"- storage_scope: {scope}\n"
        f"{sha_line}"
        "- summary: 校验 storage_scope 语义。\n"
    )


def test_storage_scope_local_sha256_match_passes(tmp_path: Path) -> None:
    _write_referenced_files(tmp_path)
    artifact = tmp_path / "reports" / "artifact.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("artifact", encoding="utf-8")
    digest = hashlib.sha256(b"artifact").hexdigest()
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text(
        "# Evidence Index\n\n"
        + _valid_entry()
        + _scope_entry("local:reports/artifact.json", digest),
        encoding="utf-8",
    )

    result = evidence_check.check_evidence_index(evidence_file)

    assert result.passed is True


def test_storage_scope_local_sha256_stale_does_not_block(tmp_path: Path) -> None:
    """local 工件为 gitignore 生成物，哈希漂移不阻断（repo 工件才强制匹配）。"""
    _write_referenced_files(tmp_path)
    artifact = tmp_path / "reports" / "artifact.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("artifact", encoding="utf-8")
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text(
        "# Evidence Index\n\n"
        + _valid_entry()
        + _scope_entry("local:reports/artifact.json", "0" * 64),
        encoding="utf-8",
    )

    result = evidence_check.check_evidence_index(evidence_file)

    assert result.passed is True


def test_storage_scope_absolute_path_requires_prefix_fails(tmp_path: Path) -> None:
    _write_referenced_files(tmp_path)
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text(
        "# Evidence Index\n\n"
        + _valid_entry()
        + _scope_entry(r"D:\Project\foo\artifact.json"),
        encoding="utf-8",
    )

    result = evidence_check.check_evidence_index(evidence_file)

    assert result.passed is False
    assert any("禁止裸路径" in issue for issue in result.issues)


def test_storage_scope_prefixed_path_allowed(tmp_path: Path) -> None:
    _write_referenced_files(tmp_path)
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text(
        "# Evidence Index\n\n"
        + _valid_entry()
        + _scope_entry("local:reports/harness/dsecrets-test-20260814.json"),
        encoding="utf-8",
    )

    result = evidence_check.check_evidence_index(evidence_file)

    assert result.passed is True


def test_sha256_map_format_checks_each_file(tmp_path: Path) -> None:
    _write_referenced_files(tmp_path)
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text("aaa", encoding="utf-8")
    b.write_text("bbb", encoding="utf-8")
    ha = hashlib.sha256(b"aaa").hexdigest()
    hb = hashlib.sha256(b"bbb").hexdigest()
    entry = (
        "\n## E-20260814-097：sha256 映射格式\n\n"
        "- trace_id: 20260814-sha-map-test\n"
        "- generated_at: 2026-08-14\n"
        "- evidence_type: governance/sha-map-test\n"
        "- file: `repo:a.json`; `repo:b.json`\n"
        "- command: `python scripts/check_evidence_index.py`\n"
        "- result: pass\n"
        "- related_logbook: 2026-08-14 - x\n"
        "- related_adr: none\n"
        "- contains_sensitive_data: no\n"
        "- retention_note: 测试。\n"
        f"- sha256: a.json={ha}；b.json={hb}\n"
        "- storage_scope: repository\n"
        "- summary: 校验多文件映射哈希。\n"
    )
    evidence_file = tmp_path / "evidence-index.md"
    evidence_file.write_text(
        "# Evidence Index\n\n" + _valid_entry() + entry, encoding="utf-8"
    )
    assert evidence_check.check_evidence_index(evidence_file).passed is True
    broken = entry.replace(hb, "0" * 64)
    evidence_file.write_text(
        "# Evidence Index\n\n" + _valid_entry() + broken, encoding="utf-8"
    )
    result = evidence_check.check_evidence_index(evidence_file)
    assert result.passed is False
    assert any("sha256 mismatch" in issue for issue in result.issues)


def _git_fixture(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=repo, capture_output=True, check=True
    )
    _write_referenced_files(repo)
    (repo / "artifact.json").write_text("artifact", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "fixture"], cwd=repo, capture_output=True, check=True
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    return repo, sha, hashlib.sha256(b"artifact").hexdigest()


def _git_entry(
    commit: str,
    sha256: str | None,
    file_ref: str,
    *,
    entry_commit: str | None = None,
) -> str:
    sha_line = f"- sha256: {sha256}\n" if sha256 else ""
    commit_line = f"- commit_sha: {entry_commit}\n" if entry_commit is not None else ""
    return (
        "\n## E-20260815-003：git 工件测试\n\n"
        "- trace_id: test\n"
        "- generated_at: 2026-08-15\n"
        "- evidence_type: governance/git-ref-test\n"
        f"- file: `{file_ref}`\n"
        "- command: x\n"
        "- result: pass\n"
        "- related_logbook: x\n"
        "- related_adr: none\n"
        "- contains_sensitive_data: no\n"
        "- retention_note: x\n"
        "- storage_scope: repository\n"
        f"{commit_line}"
        f"{sha_line}"
        "- summary: x\n"
    )


def _run_git_index(repo: Path, entry: str) -> evidence_check.EvidenceCheckResult:
    evidence_file = repo / "evidence-index.md"
    evidence_file.write_text(
        "# Evidence Index\n\n" + _valid_entry() + entry, encoding="utf-8"
    )
    return evidence_check.check_evidence_index(evidence_file)


def test_git_ref_valid_passes(tmp_path: Path, monkeypatch) -> None:
    repo, sha, digest = _git_fixture(tmp_path)
    monkeypatch.setattr(evidence_check, "ROOT_DIR", repo)
    result = _run_git_index(
        repo, _git_entry(sha, digest, f"git:{sha}:artifact.json", entry_commit=sha)
    )
    assert result.passed is True


def test_git_ref_head_rejected(tmp_path: Path, monkeypatch) -> None:
    repo, _, _ = _git_fixture(tmp_path)
    monkeypatch.setattr(evidence_check, "ROOT_DIR", repo)
    result = _run_git_index(repo, _git_entry("0" * 40, None, "git:HEAD:artifact.json"))
    assert result.passed is False
    assert any("完整 40 位 commit SHA" in issue for issue in result.issues)


def test_git_ref_short_sha_rejected(tmp_path: Path, monkeypatch) -> None:
    repo, sha, _ = _git_fixture(tmp_path)
    monkeypatch.setattr(evidence_check, "ROOT_DIR", repo)
    result = _run_git_index(
        repo, _git_entry("0" * 40, None, f"git:{sha[:8]}:artifact.json")
    )
    assert result.passed is False
    assert any("完整 40 位 commit SHA" in issue for issue in result.issues)


def test_git_ref_missing_commit_sha_fails(tmp_path: Path, monkeypatch) -> None:
    repo, sha, digest = _git_fixture(tmp_path)
    monkeypatch.setattr(evidence_check, "ROOT_DIR", repo)
    result = _run_git_index(repo, _git_entry(sha, digest, f"git:{sha}:artifact.json"))
    assert result.passed is False
    assert any("commit_sha" in issue for issue in result.issues)


def test_git_ref_commit_mismatch_fails(tmp_path: Path, monkeypatch) -> None:
    repo, sha, digest = _git_fixture(tmp_path)
    (repo / "artifact.json").write_text("artifact2", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "second"], cwd=repo, capture_output=True, check=True
    )
    second = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    monkeypatch.setattr(evidence_check, "ROOT_DIR", repo)
    result = _run_git_index(
        repo,
        _git_entry(sha, digest, f"git:{sha}:artifact.json", entry_commit=second),
    )
    assert result.passed is False
    assert any("不一致" in issue for issue in result.issues)


def test_git_blob_missing_fails(tmp_path: Path, monkeypatch) -> None:
    repo, sha, _ = _git_fixture(tmp_path)
    monkeypatch.setattr(evidence_check, "ROOT_DIR", repo)
    result = _run_git_index(
        repo, _git_entry(sha, "0" * 64, f"git:{sha}:not-exists.json", entry_commit=sha)
    )
    assert result.passed is False
    assert any("git 工件缺失" in issue for issue in result.issues)


def test_git_blob_binary_content_hash_passes(tmp_path: Path, monkeypatch) -> None:
    """批处理读取器对含非 UTF-8 字节的 blob 按原始字节计算 sha256。"""
    repo, _, _ = _git_fixture(tmp_path)
    raw = b"\x00\xff\xfe artifact \x00\n\x80"
    (repo / "bin.dat").write_bytes(raw)
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "bin"], cwd=repo, capture_output=True, check=True
    )
    bin_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    digest = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(evidence_check, "ROOT_DIR", repo)
    result = _run_git_index(
        repo,
        _git_entry(bin_sha, digest, f"git:{bin_sha}:bin.dat", entry_commit=bin_sha),
    )
    assert result.passed is True


def test_git_batch_single_process_for_all_refs(tmp_path, monkeypatch) -> None:
    """多 commit / 多 blob 引用只启动一个 `git cat-file --batch` 进程（批处理合同）。

    断言以进程启动次数为准，不引入脆弱的耗时阈值；重复检查命中模块级缓存，
    不额外启动进程。
    """
    repo, sha, artifact_digest = _git_fixture(tmp_path)
    (repo / "b.json").write_text("bbb", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "second"], cwd=repo, capture_output=True, check=True
    )
    second = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    b_digest = hashlib.sha256(b"bbb").hexdigest()

    spawns: list[tuple] = []
    real_popen = subprocess.Popen

    def counting_popen(*args, **kwargs):
        spawns.append(args)
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(evidence_check, "ROOT_DIR", repo)
    monkeypatch.setattr(evidence_check.subprocess, "Popen", counting_popen)

    entry_artifact = _git_entry(
        sha, artifact_digest, f"git:{sha}:artifact.json", entry_commit=sha
    )
    entry_b = _git_entry(
        second,
        b_digest,
        f"git:{second}:b.json",
        entry_commit=second,
    ).replace("E-20260815-003", "E-20260815-004")

    result = _run_git_index(repo, entry_artifact + entry_b)
    assert result.passed is True
    assert len(spawns) == 1

    result_again = _run_git_index(repo, entry_artifact + entry_b)
    assert result_again.passed is True
    assert len(spawns) == 1
