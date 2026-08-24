import json

import pytest

from app.models.youzan_webhook_event import (
    YouzanWebhookBusinessType,
    YouzanWebhookEventCreate,
    YouzanWebhookEventUpdate,
    YouzanWebhookStatus,
)
from app.repository.youzan_webhook_event_repo import YouzanWebhookEventRepo


@pytest.mark.asyncio
async def test_create_and_mark_youzan_webhook_event(db) -> None:
    repo = YouzanWebhookEventRepo(db)

    event_id = await repo.create_received(
        YouzanWebhookEventCreate(
            msg_id="msg-001",
            trace_id="trace-001",
            event_type="trade_TradeBuyerPay",
            business_type=YouzanWebhookBusinessType.TRADE,
            business_key="E202605240001",
            http_status=200,
            payload_hash="abc123",
            payload_summary_json=json.dumps({"tid": "E202605240001"}),
        )
    )
    await repo.mark_processing(event_id, "trade_api_fetch")
    await repo.mark_result(
        event_id,
        YouzanWebhookEventUpdate(
            status=YouzanWebhookStatus.PROCESSED,
            process_stage="trade_processed",
            business_type=YouzanWebhookBusinessType.TRADE,
            business_key="E202605240001",
        ),
    )

    row = await repo.get_by_msg_id("msg-001")
    assert row is not None
    assert row["status"] == YouzanWebhookStatus.PROCESSED
    assert row["process_stage"] == "trade_processed"
    assert row["business_key"] == "E202605240001"
    assert row["process_started_at"]
    assert row["process_finished_at"]
    assert row["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_duplicate_youzan_webhook_event_marks_existing_row(db) -> None:
    repo = YouzanWebhookEventRepo(db)
    event = YouzanWebhookEventCreate(
        msg_id="msg-dup",
        trace_id="trace-a",
        event_type="ITEM_INFO",
        business_type=YouzanWebhookBusinessType.ITEM,
        business_key="100010",
        http_status=200,
        payload_hash="hash-a",
        payload_summary_json="{}",
    )

    first_id = await repo.create_received(event)
    second_id = await repo.create_received(
        YouzanWebhookEventCreate(
            msg_id="msg-dup",
            trace_id="trace-b",
            event_type="ITEM_INFO",
            business_type=YouzanWebhookBusinessType.ITEM,
            business_key="100010",
            http_status=200,
            payload_hash="hash-b",
            payload_summary_json="{}",
        )
    )

    assert second_id == first_id
    row = await repo.get_by_msg_id("msg-dup")
    assert row is not None
    assert row["status"] == YouzanWebhookStatus.DUPLICATE
    assert row["trace_id"] == "trace-b"
