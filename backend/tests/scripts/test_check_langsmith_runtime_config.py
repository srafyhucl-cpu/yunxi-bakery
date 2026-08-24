"""LangSmith 运行时配置预检测试。"""

from __future__ import annotations

import json
from pathlib import Path

from app.service.agents.observability import AgentTracingConfig
from scripts import check_langsmith_runtime_config as preflight


def build_config(
    *,
    tracing_enabled: bool = False,
    project: str = "yunxi-bakebot",
    api_key: str = "",
) -> AgentTracingConfig:
    return AgentTracingConfig(
        langchain_tracing_enabled=tracing_enabled,
        langchain_project=project,
        langsmith_api_key=api_key,
        agent_local_trace_enabled=True,
    )


def test_disabled_config_passes_without_external_export() -> None:
    report = preflight.build_langsmith_runtime_config_report(
        config=build_config(),
        environ={},
    )

    assert report["status"] == "passed"
    assert report["runtime"]["enabled"] is False
    assert report["runtime"]["safe_to_enable"] is False
    assert report["runtime"]["missing"] == []
    assert report["boundaries"]["langsmith_external_export"] is False


def test_enabled_config_requires_api_key() -> None:
    report = preflight.build_langsmith_runtime_config_report(
        config=build_config(tracing_enabled=True),
        environ={},
    )

    assert report["status"] == "failed"
    assert report["runtime"]["enabled"] is False
    assert report["runtime"]["missing"] == ["LANGSMITH_API_KEY"]


def test_require_enabled_fails_when_tracing_is_disabled() -> None:
    report = preflight.build_langsmith_runtime_config_report(
        require_enabled=True,
        config=build_config(api_key="secret-value"),
        environ={},
    )

    assert report["status"] == "failed"
    assert "LANGCHAIN_TRACING_ENABLED" in report["runtime"]["missing"]
    assert "secret-value" not in json.dumps(report, ensure_ascii=False)


def test_env_aliases_can_make_config_ready_without_printing_key() -> None:
    report = preflight.build_langsmith_runtime_config_report(
        config=build_config(),
        environ={
            "LANGCHAIN_TRACING_V2": "true",
            "LANGCHAIN_PROJECT": "prod-project",
            "LANGCHAIN_API_KEY": "secret-value",
        },
    )
    serialized = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "passed"
    assert report["runtime"]["enabled"] is True
    assert report["runtime"]["safe_to_enable"] is True
    assert report["runtime"]["project"] == "prod-project"
    assert report["env"]["LANGCHAIN_API_KEY"] == "configured"
    assert "secret-value" not in serialized


def test_metadata_redaction_removes_sensitive_sample_values() -> None:
    report = preflight.build_langsmith_runtime_config_report(
        config=build_config(tracing_enabled=True, api_key="secret-value"),
        environ={},
    )
    serialized = json.dumps(report["metadata_redaction"]["sample"], ensure_ascii=False)

    assert report["metadata_redaction"]["status"] == "passed"
    assert report["metadata_redaction"]["sensitive_markers_found"] == []
    assert "sample-secret-api-key" not in serialized
    assert "sample-open-id" not in serialized
    assert "13800000000" not in serialized
    assert "用户原文不应外发" not in serialized


def test_cli_writes_json_report(tmp_path: Path, monkeypatch) -> None:
    output_path = tmp_path / "langsmith.json"
    monkeypatch.setattr(
        preflight,
        "get_agent_tracing_config",
        lambda: build_config(),
    )
    monkeypatch.setattr(preflight.os, "environ", {})

    exit_code = preflight.main(
        [
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["boundaries"]["business_database_read"] is False
