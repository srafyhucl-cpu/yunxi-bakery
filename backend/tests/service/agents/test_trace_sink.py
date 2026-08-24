"""Agent 本地 trace sink 合同测试。"""

import hashlib
import json
import os
import stat

import pytest

from app.service.agents.customer.service import _write_trace as write_customer_trace
from app.service.agents.trace_report import AgentTraceRun
from app.service.agents.trace_sink import (
    LocalAgentTraceSink,
    build_local_agent_trace_sink,
)


@pytest.mark.asyncio
async def test_local_trace_sink_writes_hashed_identity_and_safe_events(
    tmp_path,
) -> None:
    trace_path = tmp_path / "agent-traces" / "runtime.jsonl"
    sink = LocalAgentTraceSink(trace_path)
    trace_run = AgentTraceRun(
        agent="customer",
        conversation_id="session-secret",
        channel="youzan",
        final_status="success",
        trace_events=(
            {
                "node": "model_with_tools",
                "event": "node",
                "messages": ["secret"],
                "tool_call_count": 1,
            },
        ),
    )

    await sink.write(trace_run)

    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert "session-secret" not in json.dumps(payload, ensure_ascii=False)
    assert (
        payload["conversation_id_hash"] == hashlib.sha256(b"session-secret").hexdigest()
    )
    assert payload["trace_events"][0] == {
        "node": "model_with_tools",
        "event": "node",
        "tool_call_count": 1,
    }
    if os.name != "nt":
        assert stat.S_IMODE(trace_path.stat().st_mode) == 0o600


def test_build_local_trace_sink_requires_enabled_path() -> None:
    assert build_local_agent_trace_sink(enabled=False, path="x") is None
    assert build_local_agent_trace_sink(enabled=True, path="") is None


@pytest.mark.asyncio
async def test_trace_sink_failure_does_not_escape_customer_service() -> None:
    class FailingSink:
        async def write(self, trace_run: AgentTraceRun) -> None:
            raise OSError("sink unavailable")

    await write_customer_trace(
        FailingSink(),
        AgentTraceRun(agent="customer", trace_events=()),
    )
