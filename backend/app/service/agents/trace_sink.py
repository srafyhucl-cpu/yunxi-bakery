"""Agent 本地 trace 持久化 sink。"""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from app.service.agents.observability import safe_trace_payload
from app.service.agents.trace_report import AgentTraceRun


class AgentTraceSink(Protocol):
    """脱敏 Agent trace 的异步持久化协议。"""

    async def write(self, trace_run: AgentTraceRun) -> None:
        """持久化一条 trace。"""


class LocalAgentTraceSink:
    """以 JSONL 保存脱敏业务 SLI，不保存会话原始标识。"""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    async def write(self, trace_run: AgentTraceRun) -> None:
        payload = _build_sink_payload(trace_run)
        await asyncio.to_thread(_append_json_line, self._path, payload)


def build_local_agent_trace_sink(
    *,
    enabled: bool,
    path: str,
) -> LocalAgentTraceSink | None:
    """按配置构造本地 sink，缺少路径时保持关闭。"""
    if not enabled or not path.strip():
        return None
    return LocalAgentTraceSink(path)


def _build_sink_payload(trace_run: AgentTraceRun) -> dict[str, Any]:
    payload = trace_run.to_dict()
    conversation_id = str(payload.pop("conversation_id", "") or "")
    if conversation_id:
        payload["conversation_id_hash"] = hashlib.sha256(
            conversation_id.encode("utf-8")
        ).hexdigest()
    return safe_trace_payload(payload)


def _append_json_line(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    path.chmod(0o600)
    with path.open("a", encoding="utf-8") as trace_file:
        trace_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
