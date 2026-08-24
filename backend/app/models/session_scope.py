"""会话可见范围元数据。"""

import json
from dataclasses import dataclass
from enum import Enum

from app.utils import now_str


class SessionScope(str, Enum):
    """离线画像可见的会话材料范围。"""

    BOT_ONLY = "bot_only"
    BOT_THEN_HANDOFF_PARTIAL = "bot_then_handoff_partial"
    BOT_THEN_HUMAN_SYNCED = "bot_then_human_synced"


@dataclass(frozen=True)
class SessionScopeSnapshot:
    """从 sessions.extra_info 解析出的画像边界。"""

    session_scope: str
    handoff_occurred: bool
    human_messages_available: bool


def mark_handoff_started(extra_info: str) -> str:
    """记录会话已转人工，但人工阶段消息尚不可见。"""
    payload = _load_extra(extra_info)
    payload["session_scope"] = SessionScope.BOT_THEN_HANDOFF_PARTIAL.value
    payload["handoff_occurred"] = True
    payload["human_messages_available"] = False
    payload.setdefault("handoff_at", now_str())
    return json.dumps(payload, ensure_ascii=False)


def mark_human_messages_synced(extra_info: str) -> str:
    """记录人工阶段消息已进入本系统可见范围。"""
    payload = _load_extra(extra_info)
    payload["session_scope"] = SessionScope.BOT_THEN_HUMAN_SYNCED.value
    payload["handoff_occurred"] = True
    payload["human_messages_available"] = True
    payload["human_messages_synced_at"] = now_str()
    return json.dumps(payload, ensure_ascii=False)


def snapshot_session_scope(extra_info: str) -> SessionScopeSnapshot:
    """读取画像 Agent 需要的会话可见范围。"""
    payload = _load_extra(extra_info)
    allowed_scopes = {scope.value for scope in SessionScope}
    session_scope = str(payload.get("session_scope") or SessionScope.BOT_ONLY.value)
    if session_scope not in allowed_scopes:
        session_scope = SessionScope.BOT_ONLY.value
    return SessionScopeSnapshot(
        session_scope=session_scope,
        handoff_occurred=bool(payload.get("handoff_occurred", False)),
        human_messages_available=bool(payload.get("human_messages_available", False)),
    )


def _load_extra(extra_info: str) -> dict:
    try:
        payload = json.loads(extra_info or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
