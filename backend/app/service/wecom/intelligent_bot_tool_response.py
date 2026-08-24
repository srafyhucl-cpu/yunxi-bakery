"""企微智能机器人工具通用响应。"""

from typing import Any

DEFAULT_TOOL_LIMIT = 5
MAX_TOOL_LIMIT = 10
DISPLAY_TEXT_FIELDS = (
    "answer",
    "productsText",
    "ordersText",
    "addressesText",
    "summaryText",
    "transfersText",
    "webhooksText",
)


def extract_limit(payload: dict[str, Any]) -> int:
    raw_limit = payload.get("limit", DEFAULT_TOOL_LIMIT)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return DEFAULT_TOOL_LIMIT
    return max(1, min(limit, MAX_TOOL_LIMIT))


def ok_response(
    tool: str,
    query: str,
    summary: str,
    **extra_fields: Any,
) -> dict[str, Any]:
    result_text = _resolve_result_text(summary, extra_fields)
    return {
        "ok": True,
        "tool": tool,
        "query": query,
        "summary": summary,
        "suggestedReply": result_text,
        "result": result_text,
        "resultText": result_text,
        **extra_fields,
    }


def unavailable(tool: str, label: str) -> dict[str, Any]:
    return tool_error(tool, f"{label}工具尚未完成服务注入。", "请先检查后端服务装配。")


def missing_query(tool: str, message: str) -> dict[str, Any]:
    return tool_error(tool, message, "请补充查询关键词后重试。")


def failed(tool: str, message: str) -> dict[str, Any]:
    return tool_error(tool, message, "请稍后重试，或进入后台人工查询。")


def tool_error(tool: str, message: str, next_action: str) -> dict[str, Any]:
    return {
        "ok": False,
        "tool": tool,
        "summary": message,
        "suggestedReply": message,
        "result": message,
        "resultText": message,
        "nextAction": next_action,
    }


def _resolve_result_text(summary: str, extra_fields: dict[str, Any]) -> str:
    for field_name in DISPLAY_TEXT_FIELDS:
        value = extra_fields.get(field_name)
        if isinstance(value, str) and value.strip():
            return value
    return summary
