"""Harness P0 统一门禁入口测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import harness_p0_gate


def test_build_commands_contains_all_required_checks() -> None:
    names = [name for name, _command in harness_p0_gate.build_commands()]

    assert names == [
        "依赖锁一致性",
        "中文治理 P0",
        "策略即代码 P0",
        "运行 manifest P0",
        "项目开发总表",
        "错误账本",
        "证据索引",
        "文本编码",
        "项目红线",
    ]
    assert all(
        command[0] == harness_p0_gate.sys.executable
        for _name, command in harness_p0_gate.build_commands()
    )


def test_build_commands_passes_commit_range_to_policy_check() -> None:
    _names, policy_command = harness_p0_gate.build_commands(
        base_sha="a" * 40, head_sha="b" * 40
    )[2]

    assert "--base" in policy_command
    assert "a" * 40 in policy_command
    assert "--head" in policy_command
    assert "b" * 40 in policy_command


def test_run_gate_rejects_partial_policy_range(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="必须同时提供"):
        harness_p0_gate.run_gate(tmp_path, base_sha="a" * 40)


def test_run_check_propagates_nonzero_exit_and_captures_output(tmp_path: Path) -> None:
    result = harness_p0_gate.run_check(
        "失败检查",
        (
            harness_p0_gate.sys.executable,
            "-c",
            "import sys; print('stdout'); print('stderr', file=sys.stderr); sys.exit(3)",
        ),
        root_dir=tmp_path,
    )

    assert result.passed is False
    assert "stdout" in result.output
    assert "stderr" in result.output


def test_write_json_rejects_overwrite(tmp_path: Path) -> None:
    report_path = tmp_path / "reports" / "p0.json"
    payload = {"status": "passed"}

    harness_p0_gate.write_json(report_path, payload)

    with pytest.raises(FileExistsError, match="拒绝覆盖"):
        harness_p0_gate.write_json(report_path, payload)
    assert json.loads(report_path.read_text(encoding="utf-8")) == payload


def test_run_gate_uses_d_drive_parent_for_temporary_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, Path] = {}

    class RecordingTemporaryDirectory:
        def __init__(self, *, prefix: str, dir: Path) -> None:
            observed["parent"] = dir
            self.path = dir / f"{prefix}test"

        def __enter__(self) -> str:
            return str(self.path)

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        harness_p0_gate.tempfile, "TemporaryDirectory", RecordingTemporaryDirectory
    )
    monkeypatch.setattr(
        harness_p0_gate,
        "build_commands",
        lambda: (("检查", (harness_p0_gate.sys.executable, "-c", "pass")),),
    )
    monkeypatch.setattr(
        harness_p0_gate,
        "build_policy_snapshot",
        lambda _path: {"policy_id": "test", "schema_version": "1", "sha256": "hash"},
    )

    report = harness_p0_gate.run_gate(tmp_path)

    assert observed["parent"] == tmp_path.parent
    assert report["status"] == "passed"


def test_run_gate_marks_failed_checks_and_returns_failed_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        harness_p0_gate,
        "build_commands",
        lambda: (
            ("通过", (harness_p0_gate.sys.executable, "-c", "pass")),
            ("失败", (harness_p0_gate.sys.executable, "-c", "raise SystemExit(7)")),
        ),
    )
    monkeypatch.setattr(
        harness_p0_gate,
        "build_policy_snapshot",
        lambda _path: {"policy_id": "test", "schema_version": "1", "sha256": "hash"},
    )

    report = harness_p0_gate.run_gate(tmp_path)

    assert report["status"] == "failed"
    assert report["failed"] == 1
    assert report["issues"][0]["name"] == "失败"
