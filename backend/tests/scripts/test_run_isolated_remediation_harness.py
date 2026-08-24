"""隔离本地整改 Harness 合同测试。"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import run_isolated_remediation_harness as harness


@pytest.mark.asyncio
async def test_isolated_remediation_harness_passes_and_cleans_files(tmp_path) -> None:
    report = await harness.run_harness(tmp_path)

    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert report["metadata"] == {
        "generated_at": report["metadata"]["generated_at"],
        "isolated": True,
        "production_data_access": False,
        "legacy_auth": False,
        "external_calls": False,
    }
    assert not list(tmp_path.glob("*.db*"))
    check_names = {check["name"] for check in report["checks"]}
    assert check_names == {
        "privacy.authenticated_export",
        "privacy.authenticated_delete",
        "privacy.linked_records_removed",
        "privacy.consent_revoked",
        "queue.claimed_before_crash",
        "queue.reclaimed_after_crash",
        "queue.attempt_count_incremented",
        "queue.single_processed_terminal",
    }


def test_report_marks_failed_checks() -> None:
    report = harness.build_report(
        [
            harness.HarnessCheck("passed", True),
            harness.HarnessCheck("failed", False, "synthetic failure"),
        ]
    )

    assert report["status"] == "failed"
    assert report["failed"] == 1
    assert report["failed_names"] == ["failed"]


@pytest.mark.asyncio
async def test_main_outputs_machine_readable_report(tmp_path, capsys) -> None:
    exit_code = await harness.async_main(["--work-dir", str(tmp_path), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["failed"] == 0


def test_cli_json_stdout_is_parseable(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_isolated_remediation_harness.py",
            "--work-dir",
            str(tmp_path),
            "--json",
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["failed"] == 0
    assert not list(tmp_path.glob("*.db*"))
