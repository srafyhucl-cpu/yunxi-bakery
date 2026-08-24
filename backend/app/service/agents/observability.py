"""Agent 本地观测事件模型。"""

from dataclasses import dataclass, field
from typing import Any

DEFAULT_TRACE_EVENT_TYPE = "node"
DEFAULT_AGENT_PROJECT = "yunxi-bakebot"
SENSITIVE_METADATA_KEY_PARTS = (
    "api_key",
    "token",
    "secret",
    "password",
    "credential",
    "message",
    "history",
    "profile",
    "tool_result",
    "open_id",
    "openid",
    "phone",
    "mobile",
    "address",
)


@dataclass(frozen=True)
class AgentTraceEvent:
    """Graph 节点级本地 trace 事件。"""

    node: str
    event_type: str = DEFAULT_TRACE_EVENT_TYPE
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        event = {"node": self.node, "event": self.event_type}
        event.update(self.attributes)
        return event


@dataclass(frozen=True)
class AgentTracingConfig:
    """Agent tracing 配置快照，避免在运行时泄露密钥。"""

    langchain_tracing_enabled: bool
    langchain_project: str
    langsmith_api_key: str
    agent_local_trace_enabled: bool

    @property
    def is_langsmith_enabled(self) -> bool:
        return self.langchain_tracing_enabled and bool(self.langsmith_api_key)

    def to_langsmith_env(self) -> dict[str, str]:
        """生成可选 LangSmith 环境变量，不包含关闭态的空密钥。"""
        if not self.is_langsmith_enabled:
            return {
                "LANGCHAIN_TRACING_V2": "false",
                "LANGSMITH_TRACING": "false",
            }
        return {
            "LANGCHAIN_TRACING_V2": "true",
            "LANGSMITH_TRACING": "true",
            "LANGCHAIN_PROJECT": self.langchain_project,
            "LANGSMITH_API_KEY": self.langsmith_api_key,
        }

    def to_runnable_config(
        self,
        *,
        run_name: str,
        tags: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """构造 LangChain RunnableConfig，只放脱敏元数据。"""
        return {
            "run_name": run_name,
            "tags": list(tags),
            "metadata": {
                "agent_local_trace_enabled": self.agent_local_trace_enabled,
                "langsmith_enabled": self.is_langsmith_enabled,
                "langchain_project": self.langchain_project,
                **_safe_trace_metadata(metadata or {}),
            },
        }


def get_agent_tracing_config(config: Any | None = None) -> AgentTracingConfig:
    """从应用配置生成 Agent tracing 配置。"""
    if config is None:
        from app.config import settings as app_settings

        config = app_settings

    project = str(getattr(config, "LANGCHAIN_PROJECT", "") or DEFAULT_AGENT_PROJECT)
    return AgentTracingConfig(
        langchain_tracing_enabled=bool(
            getattr(config, "LANGCHAIN_TRACING_ENABLED", False)
        ),
        langchain_project=project,
        langsmith_api_key=str(getattr(config, "LANGSMITH_API_KEY", "") or ""),
        agent_local_trace_enabled=bool(
            getattr(config, "AGENT_LOCAL_TRACE_ENABLED", True)
        ),
    )


def _safe_trace_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return safe_trace_payload(metadata)


def safe_trace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """过滤 trace payload 中的敏感字段。"""
    safe_payload: dict[str, Any] = {}
    for key, value in payload.items():
        if _is_sensitive_metadata_key(key):
            continue
        if isinstance(value, dict):
            safe_payload[key] = safe_trace_payload(value)
        elif isinstance(value, list):
            safe_payload[key] = [
                safe_trace_payload(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            safe_payload[key] = value
    return safe_payload


def _is_sensitive_metadata_key(key: str) -> bool:
    normalized_key = key.lower()
    return any(part in normalized_key for part in SENSITIVE_METADATA_KEY_PARTS)


def build_node_trace_event(node: str, **attributes: Any) -> dict[str, Any]:
    """构造兼容现有 trace_events 的节点事件。"""
    return AgentTraceEvent(node=node, attributes=attributes).to_dict()


def append_trace_event(
    events: list[dict[str, Any]] | None,
    node: str,
    **attributes: Any,
) -> list[dict[str, Any]]:
    """返回追加节点事件后的新 trace 列表。"""
    return [
        *(events or []),
        build_node_trace_event(node, **attributes),
    ]
