"""离线 Agent 的 JSON 输出解析工具。"""

import json
from typing import Any

from app.exceptions import LLMError


def parse_json_object(content: str, error_message: str) -> dict[str, Any]:
    """从模型输出中提取 JSON 对象。"""
    payload_text = _extract_json_object(content.strip())
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise LLMError(error_message) from exc
    if not isinstance(payload, dict):
        raise LLMError(error_message)
    return payload


def _extract_json_object(content: str) -> str:
    if content.startswith("```"):
        content = content.strip("`").strip()
        if content.lower().startswith("json"):
            content = content[4:].strip()
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        return content[start : end + 1]
    return content
