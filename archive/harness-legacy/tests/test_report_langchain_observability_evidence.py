"""LangChain 观测证据报告测试。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts import report_langchain_observability_evidence as evidence


def test_observability_evidence_report_uses_trace_input(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(
        json.dumps(
            {
                "traces": [
                    {
                        "agent": "customer",
                        "trace_events": [
                            {"node": "load_session_context", "event": "node"}
                        ],
                    },
                    {
                        "agent": "employee",
                        "trace_events": [{"node": "execute_tools", "event": "node"}],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = evidence.build_observability_evidence_report(
        trace_input_path=trace_path,
        run_trace_probe=False,
    )

    assert report["status"] == "passed"
    assert report["trace"]["status"] == "ok"
    assert report["trace"]["total_runs"] == 2
    assert report["langsmith"]["api_key_configured"] is False
    assert report["boundaries"]["contains_sensitive_data"] is False


def test_observability_evidence_requires_trace_when_probe_skipped() -> None:
    report = evidence.build_observability_evidence_report(run_trace_probe=False)

    assert report["status"] == "failed"
    assert report["trace"]["status"] == "no_traces"
    assert report["failed"] >= 1


def test_langsmith_summary_redacts_api_key() -> None:
    class Config:
        LANGCHAIN_TRACING_ENABLED = True
        LANGCHAIN_PROJECT = "unit-test"
        LANGSMITH_API_KEY = "secret-value"
        AGENT_LOCAL_TRACE_ENABLED = True

    config = evidence.get_agent_tracing_config(Config)
    summary = {
        "env": evidence.safe_trace_payload(config.to_langsmith_env()),
        "api_key_configured": bool(config.langsmith_api_key),
    }

    assert summary["api_key_configured"] is True
    assert "LANGSMITH_API_KEY" not in summary["env"]


def test_cold_import_summary_fails_when_heavy_module_loaded(monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "langsmith": True,
                    "langchain_openai": False,
                    "langgraph": False,
                    "langchain_core": False,
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(evidence.subprocess, "run", fake_run)

    report = evidence.build_cold_import_summary("app.config")

    assert report["status"] == "failed"
    assert report["heavy_loaded"] == ["langsmith"]


def test_observability_evidence_cli_writes_json(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.json"
    output_path = tmp_path / "evidence.json"
    trace_path.write_text(
        json.dumps(
            [{"agent": "customer", "trace_events": [{"node": "record_trace"}]}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = evidence.main(
        [
            "--trace-input",
            str(trace_path),
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["trace"]["total_runs"] == 1
