"""观察台值守摘要聚合。"""

from app.models.content_change_history import ChangeStatus, ContentChangeHistoryEntry
from app.models.youzan_webhook_event import YouzanWebhookStatus
from app.repository.content_change_history_repo import ContentChangeHistoryRepo
from app.repository.youzan_webhook_event_repo import YouzanWebhookEventRepo

RECENT_FAILURE_LIMIT = 5
WEBHOOK_SCAN_LIMIT = 100
SLOW_WEBHOOK_THRESHOLD_MS = 3_000


async def build_operation_summary(
    history_repo: ContentChangeHistoryRepo,
    webhook_repo: YouzanWebhookEventRepo,
) -> dict:
    """构造上线值守用的观察台摘要。"""
    content_failure_count = await history_repo.count_entries(status=ChangeStatus.FAILED)
    webhook_failure_count = await webhook_repo.count_events(
        status=YouzanWebhookStatus.FAILED
    )
    webhook_processing_count = await webhook_repo.count_events(
        status=YouzanWebhookStatus.PROCESSING
    )
    recent_content_failures = await history_repo.list_entries(
        status=ChangeStatus.FAILED,
        limit=RECENT_FAILURE_LIMIT,
    )
    recent_webhook_failures = await webhook_repo.list_events(
        status=YouzanWebhookStatus.FAILED,
        limit=RECENT_FAILURE_LIMIT,
    )
    recent_webhooks = await webhook_repo.list_events(limit=WEBHOOK_SCAN_LIMIT)
    slow_webhooks = _build_slow_webhook_samples(recent_webhooks)
    needs_attention = any(
        [
            content_failure_count,
            webhook_failure_count,
            slow_webhooks,
        ]
    )
    return {
        "status": "attention" if needs_attention else "ok",
        "counts": {
            "content_change_failures": content_failure_count,
            "webhook_failures": webhook_failure_count,
            "webhook_processing": webhook_processing_count,
            "slow_webhooks": len(slow_webhooks),
        },
        "recent_failures": {
            "content_changes": [
                _format_content_failure(entry) for entry in recent_content_failures
            ],
            "webhooks": [
                _format_webhook_failure(entry) for entry in recent_webhook_failures
            ],
        },
        "slow_webhooks": slow_webhooks,
        "thresholds": {
            "slow_webhook_ms": SLOW_WEBHOOK_THRESHOLD_MS,
            "webhook_scan_limit": WEBHOOK_SCAN_LIMIT,
        },
    }


def _build_slow_webhook_samples(entries: list[dict]) -> list[dict]:
    slow_entries = [
        entry
        for entry in entries
        if _duration_ms(entry.get("duration_ms")) >= SLOW_WEBHOOK_THRESHOLD_MS
    ]
    slow_entries.sort(
        key=lambda entry: _duration_ms(entry.get("duration_ms")), reverse=True
    )
    return [
        _format_webhook_failure(entry) for entry in slow_entries[:RECENT_FAILURE_LIMIT]
    ]


def _format_content_failure(entry: ContentChangeHistoryEntry) -> dict:
    return {
        "id": entry.id,
        "entity_type": entry.entity_type,
        "entity_key": entry.entity_key,
        "title": entry.title,
        "source": entry.source,
        "error_type": entry.error_type,
        "error_message": entry.error_message,
        "occurred_at": entry.occurred_at,
    }


def _format_webhook_failure(entry: dict) -> dict:
    return {
        "id": entry["id"],
        "msg_id": entry["msg_id"],
        "event_type": entry["event_type"],
        "business_type": entry["business_type"],
        "business_key": entry["business_key"],
        "status": entry["status"],
        "process_stage": entry["process_stage"],
        "error_type": entry["error_type"],
        "error_message": entry["error_message"],
        "received_at": entry["received_at"],
        "duration_ms": entry["duration_ms"],
    }


def _duration_ms(raw_value: object) -> int:
    return int(raw_value) if isinstance(raw_value, int) else 0
