"""Agent 本地观测事件测试。"""

import subprocess
import sys

from app.service.agents.observability import (
    AgentTracingConfig,
    AgentTraceEvent,
    append_trace_event,
    build_node_trace_event,
    get_agent_tracing_config,
    safe_trace_payload,
)


def test_agent_trace_event_keeps_node_and_attributes() -> None:
    event = AgentTraceEvent(
        node="model_with_tools",
        attributes={"finish_reason": "stop"},
    )

    assert event.to_dict() == {
        "node": "model_with_tools",
        "event": "node",
        "finish_reason": "stop",
    }


def test_build_node_trace_event_returns_compatible_dict() -> None:
    event = build_node_trace_event("execute_tools", tool_round=1)

    assert event == {"node": "execute_tools", "event": "node", "tool_round": 1}


def test_append_trace_event_does_not_mutate_existing_events() -> None:
    existing = [{"node": "load_session_context", "event": "node"}]

    updated = append_trace_event(existing, "finalize_reply")

    assert existing == [{"node": "load_session_context", "event": "node"}]
    assert updated == [
        {"node": "load_session_context", "event": "node"},
        {"node": "finalize_reply", "event": "node"},
    ]


def test_agent_tracing_config_defaults_keep_langsmith_disabled() -> None:
    config = AgentTracingConfig(
        langchain_tracing_enabled=False,
        langchain_project="yunxi-bakebot",
        langsmith_api_key="secret",
        agent_local_trace_enabled=True,
    )

    assert config.is_langsmith_enabled is False
    assert config.to_langsmith_env() == {
        "LANGCHAIN_TRACING_V2": "false",
        "LANGSMITH_TRACING": "false",
    }


def test_agent_tracing_config_requires_api_key_to_enable_langsmith() -> None:
    config = AgentTracingConfig(
        langchain_tracing_enabled=True,
        langchain_project="yunxi-bakebot",
        langsmith_api_key="",
        agent_local_trace_enabled=True,
    )

    assert config.is_langsmith_enabled is False
    assert "LANGSMITH_API_KEY" not in config.to_langsmith_env()
    assert "LANGCHAIN_PROJECT" not in config.to_langsmith_env()


def test_agent_tracing_config_builds_safe_runnable_config() -> None:
    config = AgentTracingConfig(
        langchain_tracing_enabled=True,
        langchain_project="yunxi-bakebot",
        langsmith_api_key="secret",
        agent_local_trace_enabled=True,
    )

    runnable_config = config.to_runnable_config(
        run_name="customer_model_with_tools",
        tags=("customer",),
        metadata={"tool_count": 2},
    )

    assert runnable_config == {
        "run_name": "customer_model_with_tools",
        "tags": ["customer"],
        "metadata": {
            "agent_local_trace_enabled": True,
            "langsmith_enabled": True,
            "langchain_project": "yunxi-bakebot",
            "tool_count": 2,
        },
    }
    assert "secret" not in str(runnable_config)


def test_agent_tracing_config_filters_sensitive_metadata_keys() -> None:
    config = AgentTracingConfig(
        langchain_tracing_enabled=True,
        langchain_project="yunxi-bakebot",
        langsmith_api_key="secret",
        agent_local_trace_enabled=True,
    )

    runnable_config = config.to_runnable_config(
        run_name="customer_model_with_tools",
        metadata={
            "tool_count": 2,
            "api_key": "secret",
            "access_token": "token",
            "messages": ["hello"],
            "history_text": "history",
            "customer_profile": "profile",
            "tool_result": "result",
        },
    )

    assert runnable_config["metadata"] == {
        "agent_local_trace_enabled": True,
        "langsmith_enabled": True,
        "langchain_project": "yunxi-bakebot",
        "tool_count": 2,
    }


def test_safe_trace_payload_filters_nested_customer_sensitive_fields() -> None:
    payload = safe_trace_payload(
        {
            "node": "load_session_context",
            "open_id": "secret-open-id",
            "customer": {
                "phone": "13800000000",
                "safe_label": "vip",
            },
            "items": [{"address": "hidden"}, {"title": "伯牙绝弦"}],
        }
    )

    assert payload == {
        "node": "load_session_context",
        "customer": {"safe_label": "vip"},
        "items": [{}, {"title": "伯牙绝弦"}],
    }


def test_get_agent_tracing_config_reads_settings_like_object() -> None:
    class Config:
        LANGCHAIN_TRACING_ENABLED = True
        LANGCHAIN_PROJECT = "custom-project"
        LANGSMITH_API_KEY = "secret"
        AGENT_LOCAL_TRACE_ENABLED = False

    config = get_agent_tracing_config(Config())

    assert config.langchain_tracing_enabled is True
    assert config.langchain_project == "custom-project"
    assert config.langsmith_api_key == "secret"
    assert config.agent_local_trace_enabled is False
    assert config.to_langsmith_env()["LANGSMITH_API_KEY"] == "secret"


def test_get_agent_tracing_config_reads_current_settings_by_default(
    monkeypatch,
) -> None:
    class Config:
        LANGCHAIN_TRACING_ENABLED = True
        LANGCHAIN_PROJECT = "patched-project"
        LANGSMITH_API_KEY = "secret"
        AGENT_LOCAL_TRACE_ENABLED = False

    monkeypatch.setattr("app.config.settings", Config())

    config = get_agent_tracing_config()

    assert config.langchain_project == "patched-project"
    assert config.is_langsmith_enabled is True
    assert config.agent_local_trace_enabled is False


def test_observability_import_does_not_load_langchain_heavy_modules() -> None:
    command = (
        "import sys; "
        "import app.service.agents.observability; "
        "print({name: (name in sys.modules) "
        "for name in ['langsmith','langchain_openai','langgraph']})"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == (
        "{'langsmith': False, 'langchain_openai': False, 'langgraph': False}"
    )
