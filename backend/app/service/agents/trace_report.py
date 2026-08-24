"""Agent trace 本地报告模型。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.service.agents.observability import safe_trace_payload


@dataclass(frozen=True)
class AgentTraceRun:
    """单次 Agent 运行 trace。"""

    agent: str
    trace_events: tuple[dict[str, Any], ...]
    trace_id: str = ""
    conversation_id: str = ""
    channel: str = ""
    final_status: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "AgentTraceRun":
        events = payload.get("trace_events") or payload.get("events") or ()
        safe_events = tuple(event for event in events if isinstance(event, dict))
        return cls(
            agent=str(payload.get("agent") or "unknown"),
            trace_events=safe_events,
            trace_id=str(payload.get("trace_id") or ""),
            conversation_id=str(payload.get("conversation_id") or ""),
            channel=str(payload.get("channel") or ""),
            final_status=str(payload.get("final_status") or ""),
            metadata=safe_trace_payload(payload.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "trace_id": self.trace_id,
            "conversation_id": self.conversation_id,
            "channel": self.channel,
            "final_status": self.final_status,
            "metadata": self.metadata,
            "trace_events": [safe_trace_payload(event) for event in self.trace_events],
        }


@dataclass(frozen=True)
class AgentTraceSummary:
    """单个 Agent 的 trace 汇总。"""

    agent: str
    run_count: int
    node_counts: dict[str, int]
    event_counts: dict[str, int]
    fallback_count: int
    tool_call_count: int
    knowledge_hit_count: int
    average_latency_ms: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "run_count": self.run_count,
            "node_counts": self.node_counts,
            "event_counts": self.event_counts,
            "fallback_count": self.fallback_count,
            "tool_call_count": self.tool_call_count,
            "knowledge_hit_count": self.knowledge_hit_count,
            "average_latency_ms": self.average_latency_ms,
        }


@dataclass(frozen=True)
class AgentTraceReport:
    """双机器人 trace 汇总报告。"""

    status: str
    total_runs: int
    agents: tuple[AgentTraceSummary, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total_runs": self.total_runs,
            "metadata": self.metadata,
            "agents": [agent.to_dict() for agent in self.agents],
        }


def build_agent_trace_report(
    runs: tuple[AgentTraceRun, ...],
    metadata: dict[str, Any] | None = None,
) -> AgentTraceReport:
    """按 agent 聚合多次运行 trace。"""
    agents = tuple(
        _summarize_agent(agent, tuple(run for run in runs if run.agent == agent))
        for agent in sorted({run.agent for run in runs})
    )
    return AgentTraceReport(
        status="ok" if runs else "no_traces",
        total_runs=len(runs),
        agents=agents,
        metadata=safe_trace_payload(metadata or {}),
    )


def parse_trace_runs(payload: Any) -> tuple[AgentTraceRun, ...]:
    """从 JSON payload 解析 trace run 列表。"""
    if isinstance(payload, list):
        return tuple(
            AgentTraceRun.from_mapping(item)
            for item in payload
            if isinstance(item, dict)
        )
    if not isinstance(payload, dict):
        return ()
    traces = payload.get("traces") or payload.get("runs")
    if isinstance(traces, list):
        return tuple(
            AgentTraceRun.from_mapping(item)
            for item in traces
            if isinstance(item, dict)
        )
    if "trace_events" in payload or "events" in payload:
        return (AgentTraceRun.from_mapping(payload),)
    return ()


def _summarize_agent(
    agent: str,
    runs: tuple[AgentTraceRun, ...],
) -> AgentTraceSummary:
    node_counts: Counter[str] = Counter()
    event_counts: Counter[str] = Counter()
    latencies: list[float] = []
    fallback_count = 0
    tool_call_count = 0
    knowledge_hit_count = 0
    for run in runs:
        for event in run.trace_events:
            safe_event = safe_trace_payload(event)
            node_counts[str(safe_event.get("node") or "unknown")] += 1
            event_counts[str(safe_event.get("event") or "unknown")] += 1
            latency = _number_or_none(safe_event.get("latency_ms"))
            if latency is not None:
                latencies.append(latency)
            fallback_count += _is_fallback_event(safe_event)
            tool_call_count += _tool_call_count(safe_event)
            knowledge_hit_count += _knowledge_hit_count(safe_event)
    average_latency = round(sum(latencies) / len(latencies), 2) if latencies else None
    return AgentTraceSummary(
        agent=agent,
        run_count=len(runs),
        node_counts=dict(sorted(node_counts.items())),
        event_counts=dict(sorted(event_counts.items())),
        fallback_count=fallback_count,
        tool_call_count=tool_call_count,
        knowledge_hit_count=knowledge_hit_count,
        average_latency_ms=average_latency,
    )


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _is_fallback_event(event: dict[str, Any]) -> int:
    if event.get("fallback_reason"):
        return 1
    if event.get("finish_reason") == "fallback":
        return 1
    if event.get("final_status") == "fallback":
        return 1
    return 0


def _tool_call_count(event: dict[str, Any]) -> int:
    if isinstance(event.get("tool_name"), str) and event["tool_name"]:
        return 1
    count = event.get("tool_call_count") or event.get("count")
    return int(count) if isinstance(count, int) and count > 0 else 0


def _knowledge_hit_count(event: dict[str, Any]) -> int:
    entry_ids = event.get("knowledge_entry_ids")
    if isinstance(entry_ids, list):
        return len(entry_ids)
    count = event.get("knowledge_hit_count")
    return int(count) if isinstance(count, int) and count > 0 else 0
