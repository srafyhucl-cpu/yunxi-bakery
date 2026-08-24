"""Agent trace 报告测试。"""

from __future__ import annotations

from app.service.agents.trace_report import (
    AgentTraceRun,
    build_agent_trace_report,
    parse_trace_runs,
)


def test_build_agent_trace_report_summarizes_customer_and_employee() -> None:
    runs = (
        AgentTraceRun.from_mapping(
            {
                "agent": "customer",
                "trace_events": [
                    {"node": "model_with_tools", "event": "node", "latency_ms": 120},
                    {
                        "node": "execute_tools",
                        "event": "node",
                        "tool_name": "search_knowledge",
                    },
                    {
                        "node": "record_trace",
                        "event": "node",
                        "knowledge_entry_ids": [1, 2],
                    },
                ],
            }
        ),
        AgentTraceRun.from_mapping(
            {
                "agent": "employee",
                "trace_events": [
                    {"node": "plan_intent", "event": "node", "latency_ms": 30},
                    {"node": "execute_tools", "event": "node", "count": 2},
                    {"node": "record_trace", "event": "node"},
                ],
            }
        ),
    )

    report = build_agent_trace_report(runs).to_dict()

    assert report["status"] == "ok"
    assert report["total_runs"] == 2
    assert [agent["agent"] for agent in report["agents"]] == [
        "customer",
        "employee",
    ]
    assert report["agents"][0]["tool_call_count"] == 1
    assert report["agents"][0]["knowledge_hit_count"] == 2
    assert report["agents"][0]["average_latency_ms"] == 120
    assert report["agents"][1]["tool_call_count"] == 2


def test_build_agent_trace_report_counts_fallback_events() -> None:
    report = build_agent_trace_report(
        (
            AgentTraceRun.from_mapping(
                {
                    "agent": "customer",
                    "trace_events": [
                        {
                            "node": "model_with_tools",
                            "event": "node",
                            "finish_reason": "fallback",
                        },
                        {
                            "node": "finalize_reply",
                            "event": "node",
                            "fallback_reason": "llm_timeout",
                        },
                    ],
                }
            ),
        )
    ).to_dict()

    assert report["agents"][0]["fallback_count"] == 2


def test_trace_report_filters_sensitive_payload_fields() -> None:
    report = build_agent_trace_report(
        (
            AgentTraceRun.from_mapping(
                {
                    "agent": "customer",
                    "trace_events": [
                        {
                            "node": "load_session_context",
                            "event": "node",
                            "open_id": "secret-open-id",
                            "phone": "13800000000",
                            "address": "hidden",
                        }
                    ],
                    "metadata": {"access_token": "secret-token"},
                }
            ),
        ),
        metadata={"mobile": "13800000000", "safe": "ok"},
    ).to_dict()

    assert "secret-open-id" not in str(report)
    assert "13800000000" not in str(report)
    assert "hidden" not in str(report)
    assert "secret-token" not in str(report)
    assert report["metadata"] == {"safe": "ok"}


def test_parse_trace_runs_accepts_single_and_batch_payloads() -> None:
    single = parse_trace_runs(
        {"agent": "customer", "trace_events": [{"node": "record_trace"}]}
    )
    batch = parse_trace_runs(
        {
            "traces": [
                {"agent": "customer", "trace_events": []},
                {"agent": "employee", "events": []},
            ]
        }
    )

    assert len(single) == 1
    assert len(batch) == 2
