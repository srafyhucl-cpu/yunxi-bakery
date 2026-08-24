"""离线画像结果合并工具。"""

import json
from typing import Protocol

from app.service.offline.quality_signals import MemorySignal


class CustomerMemoryPayload(Protocol):
    """画像解析结果的最小结构。"""

    display_name: str
    preferences_json: str
    order_summary_json: str
    special_dates_json: str
    allergens_json: str
    consent_status: str


def merge_memory_signal(
    parsed: CustomerMemoryPayload,
    signal: MemorySignal,
) -> dict[str, str]:
    """把规则识别到的服务事实合入模型画像。"""
    if not signal.has_fact():
        return _as_payload(parsed)
    return {
        "display_name": parsed.display_name,
        "preferences_json": _merge_json_objects(
            parsed.preferences_json, signal.preferences
        ),
        "order_summary_json": _merge_json_objects(
            parsed.order_summary_json, signal.order_summary
        ),
        "special_dates_json": _merge_json_list_values(
            parsed.special_dates_json, signal.special_dates
        ),
        "allergens_json": _merge_json_list_values(
            parsed.allergens_json, signal.allergens
        ),
        "consent_status": parsed.consent_status,
    }


def merge_json_objects(current_json: str, existing_json: str) -> str:
    """合并画像对象字段，保留既有事实并追加新事实。"""
    existing = _loads_object(existing_json)
    current = _loads_object(current_json)
    merged = {**existing}
    for key, value in current.items():
        if key not in merged:
            merged[key] = value
        elif merged[key] != value:
            merged[key] = _merge_conflicting_values(merged[key], value)
    return json.dumps(merged, ensure_ascii=False)


def merge_json_lists(current_json: str, existing_json: str) -> str:
    """合并画像列表字段，按 JSON 表达去重。"""
    return _merge_json_list_values(existing_json, _loads_list(current_json))


def _as_payload(parsed: CustomerMemoryPayload) -> dict[str, str]:
    return {
        "display_name": parsed.display_name,
        "preferences_json": parsed.preferences_json,
        "order_summary_json": parsed.order_summary_json,
        "special_dates_json": parsed.special_dates_json,
        "allergens_json": parsed.allergens_json,
        "consent_status": parsed.consent_status,
    }


def _merge_json_objects(raw_json: str, additions: dict[str, object]) -> str:
    try:
        parsed = json.loads(raw_json or "{}")
    except json.JSONDecodeError:
        parsed = {}
    payload = parsed if isinstance(parsed, dict) else {}
    for key, value in additions.items():
        payload.setdefault(key, value)
    return json.dumps(payload, ensure_ascii=False)


def _merge_conflicting_values(existing_value: object, current_value: object) -> object:
    if isinstance(existing_value, list):
        values = existing_value
    else:
        values = [existing_value]
    if current_value not in values:
        values.append(current_value)
    return values


def _loads_object(raw_json: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw_json or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _merge_json_list_values(raw_json: str, additions: list[object]) -> str:
    existing_items = _loads_list(raw_json)
    if not additions:
        return json.dumps(existing_items, ensure_ascii=False)
    merged: list[object] = []
    seen: set[str] = set()
    for item in [*existing_items, *additions]:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        merged.append(item)
        seen.add(key)
    return json.dumps(merged, ensure_ascii=False)


def _loads_list(raw_json: str) -> list[object]:
    try:
        parsed = json.loads(raw_json or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []
