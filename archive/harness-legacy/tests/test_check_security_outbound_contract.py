"""R3-B 安全出站聚合门禁测试。"""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import check_security_outbound_contract as contract


def ready_production_state() -> dict[str, bool | int]:
    return {
        "employee_auth_required": True,
        "employee_allowed_users_count": 1,
        "employee_corp_configured": True,
        "employee_ops_users_count": 1,
        "remote_image_allowed_hosts_count": 1,
    }


def test_local_contract_passes_without_network() -> None:
    report = contract.build_report()

    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert report["assertions"]["download.consumers_use_single_policy"] is True
    assert report["assertions"]["employee.agent_checks_tools_before_execution"] is True
    assert report["assertions"]["production_runtime.checked"] is False


def test_production_contract_rejects_missing_ops_users() -> None:
    state = ready_production_state()
    state["employee_ops_users_count"] = 0

    report = contract.build_report(production_state=state)

    assert report["status"] == "failed"
    assert "production_runtime.security_config_ready" in report["failed_names"]


def test_read_production_state_accepts_only_anonymous_counts() -> None:
    completed = subprocess.CompletedProcess(
        [], 0, stdout=json.dumps(ready_production_state()), stderr=""
    )
    with patch.object(contract.subprocess, "run", return_value=completed):
        state = contract.read_production_state(Path("ssh-key"), "host", "user")

    assert state == ready_production_state()


def test_read_production_state_rejects_partial_payload() -> None:
    completed = subprocess.CompletedProcess(
        [], 0, stdout=json.dumps({"employee_auth_required": True}), stderr=""
    )
    with (
        patch.object(contract.subprocess, "run", return_value=completed),
        pytest.raises(ValueError, match="字段不完整"),
    ):
        contract.read_production_state(Path("ssh-key"), "host", "user")
