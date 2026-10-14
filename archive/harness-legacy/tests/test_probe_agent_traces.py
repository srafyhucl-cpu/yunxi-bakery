"""Agent trace 探针脚本测试。"""

from __future__ import annotations

import json
import asyncio
from pathlib import Path

from scripts import probe_agent_traces, report_agent_traces


def test_probe_agent_traces_writes_customer_and_employee_runs(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "agent-traces.json"

    result_path = asyncio.run(probe_agent_traces.main_async(output_path))

    assert result_path == output_path
    assert output_path.exists()


def test_probe_agent_traces_output_can_be_reported(
    tmp_path: Path,
    capsys,
) -> None:
    output_path = tmp_path / "agent-traces.json"

    asyncio.run(probe_agent_traces.main_async(output_path))
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert [trace["agent"] for trace in payload["traces"]] == [
        "customer",
        "employee",
    ]
    exit_code = report_agent_traces.main(["--input", str(output_path), "--summary"])

    assert exit_code == 0
    assert "agent_traces status=ok total_runs=2 agents=2" in capsys.readouterr().out
