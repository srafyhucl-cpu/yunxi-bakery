"""Render customer profile memory into read-only LLM hints."""

import json
from typing import Any

from app.models.customer_profile import CustomerProfile
from app.service.privacy_redaction import redact_external_text

PROFILE_EMPTY_SECTION = ""


def render_customer_profile(profile: CustomerProfile | None) -> str:
    """Render customer memory as read-only service hints for the bot."""
    if profile is None:
        return PROFILE_EMPTY_SECTION

    lines: list[str] = []
    if profile.display_name:
        lines.append(f"顾客称呼：{profile.display_name}")

    preferences = _render_json_value(profile.preferences_json)
    if preferences:
        lines.append(f"顾客偏好：{preferences}")

    order_summary = _render_json_value(profile.order_summary_json)
    if order_summary:
        lines.append(f"最近订单摘要：{order_summary}")

    special_dates = _render_json_value(profile.special_dates_json)
    if special_dates:
        lines.append(
            "特殊日期提醒："
            f"{special_dates}。仅作为服务提醒，涉及日期和对象时先自然核对，不要主动暴露隐私。"
        )

    allergens = _render_json_value(profile.allergens_json)
    if allergens:
        lines.append(
            f"该顾客登记过敏原：{allergens}。涉及成分时主动提醒顾客核对，"
            "不要替顾客判断能否食用。"
        )

    if not lines:
        return PROFILE_EMPTY_SECTION
    return redact_external_text(
        "## 顾客档案\n" + "\n".join(f"- {line}" for line in lines) + "\n"
    )


def _render_json_value(raw_json: str) -> str:
    try:
        parsed = json.loads(raw_json or "")
    except json.JSONDecodeError:
        return raw_json.strip()
    return _render_value(parsed)


def _render_value(value: Any) -> str:
    if value in ({}, [], "", None):
        return ""
    if isinstance(value, dict):
        parts = [
            f"{key}: {_render_value(item)}"
            for key, item in value.items()
            if item not in ("", None, [], {})
        ]
        return "、".join(parts)
    if isinstance(value, list):
        return "；".join(
            _render_value(item) for item in value if item not in ("", None, [], {})
        )
    return str(value)
