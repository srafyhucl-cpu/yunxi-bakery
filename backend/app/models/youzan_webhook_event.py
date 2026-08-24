"""Youzan webhook audit event models."""

from dataclasses import dataclass


class YouzanWebhookStatus:
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    SKIPPED = "skipped"
    FAILED = "failed"
    DUPLICATE = "duplicate"


class YouzanWebhookBusinessType:
    TRADE = "trade"
    ITEM = "item"
    CHAT = "chat"
    MEMBER = "member"
    UNKNOWN = "unknown"


@dataclass
class YouzanWebhookEventCreate:
    msg_id: str
    trace_id: str
    event_type: str
    business_type: str
    business_key: str
    http_status: int
    payload_hash: str
    payload_summary_json: str


@dataclass
class YouzanWebhookEventUpdate:
    status: str
    process_stage: str = ""
    business_type: str | None = None
    business_key: str | None = None
    error_type: str = ""
    error_message: str = ""
