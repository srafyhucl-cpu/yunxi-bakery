"""Observability models for content change history."""

from dataclasses import dataclass


class SyncSource:
    LEGACY_UNKNOWN = "legacy_unknown"
    YOUZAN_WEBHOOK = "youzan_webhook"
    CHAT_LIVE_REFRESH = "chat_live_refresh"
    SEED_KNOWLEDGE = "seed_knowledge"
    ADMIN_MANUAL = "admin_manual"


class ChangeEntityType:
    PRODUCT = "product"
    KNOWLEDGE = "knowledge"


class ChangeStatus:
    SUCCESS = "success"
    FAILED = "failed"


class ChangeAction:
    CREATE = "create"
    UPDATE = "update"
    UPSERT = "upsert"
    DEACTIVATE = "deactivate"
    ACTIVATE = "activate"
    SEED = "seed"
    SYNC_RETRY = "sync_retry"


class WriteResult:
    APPLIED = "applied"
    SKIPPED = "skipped_stale_or_same"
    FAILED = "failed"


@dataclass
class ContentChangeHistoryEntry:
    id: int = 0
    entity_type: str = ""
    entity_key: str = ""
    category: str = ""
    title: str = ""
    source: str = ""
    source_ref: str = ""
    session_id: str = ""
    webhook_msg_id: str = ""
    action: str = ""
    status: str = ""
    change_summary_json: str = "{}"
    error_type: str = ""
    error_message: str = ""
    occurred_at: str = ""
    webhook_event_type: str = ""


@dataclass
class ContentChangeHistoryCreate:
    entity_type: str
    entity_key: str
    category: str
    title: str
    source: str
    source_ref: str = ""
    session_id: str = ""
    webhook_msg_id: str = ""
    action: str = ""
    status: str = ChangeStatus.SUCCESS
    change_summary_json: str = "{}"
    error_type: str = ""
    error_message: str = ""
    occurred_at: str = ""
