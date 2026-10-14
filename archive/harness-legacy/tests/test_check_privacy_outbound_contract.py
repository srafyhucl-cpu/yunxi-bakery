"""完整隐私出站聚合门禁测试。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import check_privacy_outbound_contract as contract


def safe_production_flags() -> dict[str, bool]:
    return {flag: False for flag in contract.PRODUCTION_SAFE_FLAGS}


def test_local_contract_discovers_all_model_boundaries() -> None:
    report = contract.build_report()

    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert len(report["static"]["model_call_files"]) >= 8
    assert report["assertions"]["model_calls.all_use_redaction"] is True
    assert report["assertions"]["dynamic_payload.no_sensitive_values"] is True
    assert report["assertions"]["trace_metadata.no_sensitive_values"] is True
    assert report["assertions"]["production_runtime.checked"] is False


def test_production_contract_rejects_enabled_external_path() -> None:
    production_flags = safe_production_flags()
    production_flags["ENABLE_OFFLINE_QA"] = True

    report = contract.build_report(production_flags=production_flags)

    assert report["status"] == "failed"
    assert "production_runtime.external_paths_disabled" in report["failed_names"]


def test_read_production_flags_only_accepts_complete_boolean_report() -> None:
    completed = subprocess.CompletedProcess(
        [], 0, stdout=json.dumps(safe_production_flags()), stderr=""
    )
    with patch.object(contract.subprocess, "run", return_value=completed):
        flags = contract.read_production_flags(Path("ssh-key"), "host", "user")

    assert flags == safe_production_flags()


def test_read_production_flags_rejects_partial_report() -> None:
    completed = subprocess.CompletedProcess(
        [], 0, stdout=json.dumps({"ENABLE_OFFLINE_QA": False}), stderr=""
    )
    with (
        patch.object(contract.subprocess, "run", return_value=completed),
        pytest.raises(ValueError, match="字段不完整"),
    ):
        contract.read_production_flags(Path("ssh-key"), "host", "user")
