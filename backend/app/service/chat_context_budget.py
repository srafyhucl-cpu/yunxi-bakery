"""客户机器人上下文预算观测。"""

import json
from dataclasses import asdict, dataclass

from app.models.customer_profile import CustomerProfile
from app.models.knowledge import KnowledgeEntry
from app.service.agents.messages import (
    message_content,
    message_role,
    message_tool_calls,
)
from app.service.llm.profile_prompt import render_customer_profile
from app.service.session_manager import CONVERSATION_TOKEN_BUDGET, estimate_tokens

LONG_TERM_MEMORY_POLICY = "read_only_prompt_hints"
TOOL_CONTEXT_POLICY = "observed_runtime_tool_messages"
SUMMARY_CANDIDATE_POLICY = "observe_only_no_summary_write"
BUDGET_PRESSURE_LEVEL_NORMAL = "normal"
BUDGET_PRESSURE_LEVEL_WATCH = "watch"
BUDGET_PRESSURE_LEVEL_CRITICAL = "critical"
BUDGET_PRESSURE_WATCH_RATIO = 0.7
BUDGET_PRESSURE_CRITICAL_RATIO = 0.9


@dataclass(frozen=True)
class ChatContextBudgetSnapshot:
    """一次客服回复构造时的上下文预算快照。"""

    history_token_budget: int
    history_message_count: int
    history_token_estimate: int
    knowledge_entry_limit: int
    knowledge_entry_count: int
    knowledge_token_estimate: int
    customer_profile_present: bool
    customer_profile_token_estimate: int
    system_prompt_token_estimate: int
    total_prompt_token_estimate: int
    long_term_memory_policy: str
    conversation_summary_present: bool
    conversation_summary_token_estimate: int
    conversation_summary_policy: str
    history_budget_ratio: float
    prompt_budget_ratio: float
    budget_pressure_level: str
    needs_session_summary_candidate: bool
    summary_candidate_policy: str
    tool_context_message_count: int = 0
    tool_context_token_estimate: int = 0
    tool_result_message_count: int = 0
    tool_result_token_estimate: int = 0
    tool_context_policy: str = TOOL_CONTEXT_POLICY

    def to_dict(self) -> dict[str, int | float | bool | str]:
        return asdict(self)


def build_chat_context_budget_snapshot(
    *,
    system_prompt: str,
    history: list[dict],
    knowledge_entries: list[KnowledgeEntry],
    knowledge_entry_limit: int,
    customer_profile: CustomerProfile | None,
    conversation_summary_text: str = "",
) -> ChatContextBudgetSnapshot:
    history_token_estimate = sum(
        estimate_tokens(_message_content_text(message)) for message in history
    )
    knowledge_token_estimate = sum(
        estimate_tokens(f"{entry.title}\n{entry.content}")
        for entry in knowledge_entries
    )
    customer_profile_text = render_customer_profile(customer_profile)
    customer_profile_token_estimate = estimate_tokens(customer_profile_text)
    conversation_summary_token_estimate = estimate_tokens(conversation_summary_text)
    system_prompt_token_estimate = estimate_tokens(system_prompt)
    total_prompt_token_estimate = system_prompt_token_estimate + history_token_estimate
    pressure_fields = _build_budget_pressure_fields(
        history_token_estimate=history_token_estimate,
        total_prompt_token_estimate=total_prompt_token_estimate,
    )
    return ChatContextBudgetSnapshot(
        history_token_budget=CONVERSATION_TOKEN_BUDGET,
        history_message_count=len(history),
        history_token_estimate=history_token_estimate,
        knowledge_entry_limit=knowledge_entry_limit,
        knowledge_entry_count=len(knowledge_entries),
        knowledge_token_estimate=knowledge_token_estimate,
        customer_profile_present=customer_profile is not None,
        customer_profile_token_estimate=customer_profile_token_estimate,
        system_prompt_token_estimate=system_prompt_token_estimate,
        total_prompt_token_estimate=total_prompt_token_estimate,
        long_term_memory_policy=LONG_TERM_MEMORY_POLICY,
        conversation_summary_present=bool(conversation_summary_text.strip()),
        conversation_summary_token_estimate=conversation_summary_token_estimate,
        conversation_summary_policy="read_only_short_term_context",
        history_budget_ratio=pressure_fields["history_budget_ratio"],
        prompt_budget_ratio=pressure_fields["prompt_budget_ratio"],
        budget_pressure_level=pressure_fields["budget_pressure_level"],
        needs_session_summary_candidate=pressure_fields[
            "needs_session_summary_candidate"
        ],
        summary_candidate_policy=SUMMARY_CANDIDATE_POLICY,
    )


def record_tool_context_budget_delta(
    timing: dict | None,
    tool_context_messages: list[object],
) -> None:
    """把工具轮次新增消息合并进上下文预算观测。"""
    if timing is None or not tool_context_messages:
        return

    context_budget = timing.setdefault("context_budget", {})
    if not isinstance(context_budget, dict):
        context_budget = {}
        timing["context_budget"] = context_budget

    tool_context_token_estimate = sum(
        estimate_tokens(_message_observable_text(message))
        for message in tool_context_messages
    )
    tool_result_messages = [
        message for message in tool_context_messages if message_role(message) == "tool"
    ]
    tool_result_token_estimate = sum(
        estimate_tokens(_message_content_text(message))
        for message in tool_result_messages
    )
    _add_budget_int(
        context_budget,
        "tool_context_message_count",
        len(tool_context_messages),
    )
    _add_budget_int(
        context_budget,
        "tool_context_token_estimate",
        tool_context_token_estimate,
    )
    _add_budget_int(
        context_budget,
        "tool_result_message_count",
        len(tool_result_messages),
    )
    _add_budget_int(
        context_budget,
        "tool_result_token_estimate",
        tool_result_token_estimate,
    )
    _add_budget_int(
        context_budget,
        "total_prompt_token_estimate",
        tool_context_token_estimate,
    )
    _refresh_budget_pressure_fields(context_budget)
    context_budget["tool_context_policy"] = TOOL_CONTEXT_POLICY


def _message_content_text(message: object) -> str:
    content = message_content(message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def _message_observable_text(message: object) -> str:
    parts = [_message_content_text(message)]
    tool_calls = message_tool_calls(message)
    if tool_calls:
        parts.append(json.dumps(tool_calls, ensure_ascii=False, default=str))
    return "\n".join(part for part in parts if part)


def _add_budget_int(context_budget: dict, key: str, value: int) -> None:
    current_value = context_budget.get(key, 0)
    if not isinstance(current_value, int):
        current_value = 0
    context_budget[key] = current_value + value


def _build_budget_pressure_fields(
    *,
    history_token_estimate: int,
    total_prompt_token_estimate: int,
) -> dict[str, float | bool | str]:
    history_budget_ratio = _budget_ratio(history_token_estimate)
    prompt_budget_ratio = _budget_ratio(total_prompt_token_estimate)
    return {
        "history_budget_ratio": history_budget_ratio,
        "prompt_budget_ratio": prompt_budget_ratio,
        "budget_pressure_level": _budget_pressure_level(prompt_budget_ratio),
        "needs_session_summary_candidate": history_budget_ratio
        >= BUDGET_PRESSURE_WATCH_RATIO,
    }


def _refresh_budget_pressure_fields(context_budget: dict) -> None:
    history_token_estimate = context_budget.get("history_token_estimate", 0)
    total_prompt_token_estimate = context_budget.get("total_prompt_token_estimate", 0)
    if not isinstance(history_token_estimate, int):
        history_token_estimate = 0
    if not isinstance(total_prompt_token_estimate, int):
        total_prompt_token_estimate = 0

    context_budget.update(
        _build_budget_pressure_fields(
            history_token_estimate=history_token_estimate,
            total_prompt_token_estimate=total_prompt_token_estimate,
        )
    )
    context_budget.setdefault("summary_candidate_policy", SUMMARY_CANDIDATE_POLICY)


def _budget_ratio(token_estimate: int) -> float:
    return round(token_estimate / CONVERSATION_TOKEN_BUDGET, 4)


def _budget_pressure_level(prompt_budget_ratio: float) -> str:
    if prompt_budget_ratio >= BUDGET_PRESSURE_CRITICAL_RATIO:
        return BUDGET_PRESSURE_LEVEL_CRITICAL
    if prompt_budget_ratio >= BUDGET_PRESSURE_WATCH_RATIO:
        return BUDGET_PRESSURE_LEVEL_WATCH
    return BUDGET_PRESSURE_LEVEL_NORMAL
