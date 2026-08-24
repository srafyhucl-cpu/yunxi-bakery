"""Agent trace 报告脚本测试。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import report_agent_traces


def test_report_agent_traces_outputs_json_from_input(
    tmp_path: Path,
    capsys,
) -> None:
    trace_path = tmp_path / "agent-traces.json"
    trace_path.write_text(
        json.dumps(
            {
                "traces": [
                    {
                        "agent": "customer",
                        "trace_events": [
                            {"node": "load_session_context", "event": "node"},
                            {"node": "model_with_tools", "event": "node"},
                        ],
                    },
                    {
                        "agent": "employee",
                        "trace_events": [
                            {"node": "load_employee_context", "event": "node"},
                            {"node": "execute_tools", "event": "node", "count": 1},
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = report_agent_traces.main(["--input", str(trace_path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["total_runs"] == 2
    assert [agent["agent"] for agent in payload["agents"]] == [
        "customer",
        "employee",
    ]


def test_report_agent_traces_latest_summary_uses_newest_file(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    trace_dir = tmp_path / "agent-traces"
    trace_dir.mkdir()
    old_path = trace_dir / "old.json"
    new_path = trace_dir / "new.json"
    old_path.write_text("[]", encoding="utf-8")
    new_path.write_text(
        json.dumps(
            [
                {
                    "agent": "employee",
                    "trace_events": [{"node": "record_trace", "event": "node"}],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(report_agent_traces, "DEFAULT_TRACE_DIR", trace_dir)

    exit_code = report_agent_traces.main(["--latest", "--summary"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "agent_traces status=ok total_runs=1 agents=1" in output


def test_report_agent_traces_without_file_returns_no_traces(capsys) -> None:
    exit_code = report_agent_traces.main(["--summary"])

    assert exit_code == 0
    assert (
        "agent_traces status=no_traces total_runs=0 agents=0" in capsys.readouterr().out
    )
