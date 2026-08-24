import json

import pytest

from app.models.content_change_history import (
    ChangeAction,
    ChangeEntityType,
    ChangeStatus,
    ContentChangeHistoryCreate,
    SyncSource,
)
from app.models.youzan_webhook_event import (
    YouzanWebhookEventCreate,
    YouzanWebhookStatus,
)
from app.repository.content_change_history_repo import ContentChangeHistoryRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.repository.youzan_webhook_event_repo import YouzanWebhookEventRepo
from app.service.observability import ObservabilityService


@pytest.mark.asyncio
async def test_observability_service_lists_current_history_and_webhooks(db) -> None:
    knowledge_repo = KnowledgeRepo(db)
    product_repo = YouzanProductRepo(db)
    history_repo = ContentChangeHistoryRepo(db)
    webhook_repo = YouzanWebhookEventRepo(db)

    await knowledge_repo.insert_entry(
        category="faq",
        title="配送说明",
        content="当天配送",
        keywords="配送",
        priority=5,
        sync_source=SyncSource.SEED_KNOWLEDGE,
    )
    await product_repo.upsert_product(
        item_id=10001,
        title="芒果蛋糕",
        alias="mg001",
        price_fen=9800,
        stock=12,
        image="",
        is_active=1,
        updated_at="2026-05-25 11:00:00",
        desc="新鲜芒果",
        tags="在售, 芒果",
        sync_source=SyncSource.YOUZAN_WEBHOOK,
        sync_ref="10001",
    )
    await history_repo.add(
        ContentChangeHistoryCreate(
            entity_type=ChangeEntityType.PRODUCT,
            entity_key="10001",
            category="product",
            title="芒果蛋糕",
            source=SyncSource.YOUZAN_WEBHOOK,
            source_ref="10001",
            action=ChangeAction.UPSERT,
            status=ChangeStatus.SUCCESS,
            change_summary_json=json.dumps({"price_fen": 9800}, ensure_ascii=False),
            occurred_at="2026-05-25 11:00:00",
        )
    )
    webhook_id = await webhook_repo.create_received(
        YouzanWebhookEventCreate(
            msg_id="msg-10001",
            trace_id="trace-1",
            event_type="ITEM_INFO",
            business_type="item",
            business_key="10001",
            http_status=200,
            payload_hash="hash",
            payload_summary_json=json.dumps({"item_id": 10001}, ensure_ascii=False),
        )
    )
    await webhook_repo.mark_result(
        webhook_id,
        type(
            "Update",
            (),
            {
                "status": "failed",
                "process_stage": "item_failed",
                "business_type": "item",
                "business_key": "10001",
                "error_type": "ValueError",
                "error_message": "bad payload",
            },
        )(),
    )

    service = ObservabilityService(
        knowledge_repo=knowledge_repo,
        product_repo=product_repo,
        history_repo=history_repo,
        webhook_repo=webhook_repo,
    )
    current_items, current_total = await service.list_current_content(
        view="knowledge", keyword="配送"
    )
    history_items, history_total = await service.get_history(
        source=SyncSource.YOUZAN_WEBHOOK
    )
    webhook_items, webhook_total = await service.get_webhooks(status="failed")

    assert current_total == 1
    assert current_items[0]["title"] == "配送说明"
    assert history_total == 1
    assert history_items[0]["title"] == "芒果蛋糕"
    assert webhook_total == 1
    assert webhook_items[0]["error_message"] == "bad payload"


@pytest.mark.asyncio
async def test_observability_service_summary_flags_failures_and_slow_webhooks(
    db,
) -> None:
    knowledge_repo = KnowledgeRepo(db)
    product_repo = YouzanProductRepo(db)
    history_repo = ContentChangeHistoryRepo(db)
    webhook_repo = YouzanWebhookEventRepo(db)
    await history_repo.add(
        ContentChangeHistoryCreate(
            entity_type=ChangeEntityType.PRODUCT,
            entity_key="10002",
            category="product",
            title="榴莲蛋糕",
            source=SyncSource.YOUZAN_WEBHOOK,
            source_ref="10002",
            action=ChangeAction.UPSERT,
            status=ChangeStatus.FAILED,
            change_summary_json=json.dumps({"item_id": 10002}, ensure_ascii=False),
            error_type="RuntimeError",
            error_message="sync failed",
            occurred_at="2026-06-11 10:00:00",
        )
    )
    failed_webhook_id = await webhook_repo.create_received(
        YouzanWebhookEventCreate(
            msg_id="msg-failed",
            trace_id="trace-failed",
            event_type="ITEM_INFO",
            business_type="item",
            business_key="10002",
            http_status=200,
            payload_hash="hash-failed",
            payload_summary_json=json.dumps({"item_id": 10002}, ensure_ascii=False),
        )
    )
    await webhook_repo.mark_result(
        failed_webhook_id,
        type(
            "Update",
            (),
            {
                "status": YouzanWebhookStatus.FAILED,
                "process_stage": "item_failed",
                "business_type": "item",
                "business_key": "10002",
                "error_type": "RuntimeError",
                "error_message": "bad item payload",
            },
        )(),
    )
    slow_webhook_id = await webhook_repo.create_received(
        YouzanWebhookEventCreate(
            msg_id="msg-slow",
            trace_id="trace-slow",
            event_type="TRADE_ORDER_STATE",
            business_type="trade",
            business_key="order-1",
            http_status=200,
            payload_hash="hash-slow",
            payload_summary_json=json.dumps({"tid": "order-1"}, ensure_ascii=False),
        )
    )
    await db.execute(
        "UPDATE youzan_webhook_events SET status = ?, duration_ms = ? WHERE id = ?",
        (YouzanWebhookStatus.PROCESSED, 4500, slow_webhook_id),
    )
    await db.commit()

    service = ObservabilityService(
        knowledge_repo=knowledge_repo,
        product_repo=product_repo,
        history_repo=history_repo,
        webhook_repo=webhook_repo,
    )

    summary = await service.get_summary()

    assert summary["status"] == "attention"
    assert summary["counts"]["content_change_failures"] == 1
    assert summary["counts"]["webhook_failures"] == 1
    assert summary["counts"]["slow_webhooks"] == 1
    assert (
        summary["recent_failures"]["content_changes"][0]["error_message"]
        == "sync failed"
    )
    assert summary["recent_failures"]["webhooks"][0]["msg_id"] == "msg-failed"
    assert summary["slow_webhooks"][0]["msg_id"] == "msg-slow"


@pytest.mark.asyncio
async def test_observability_service_summary_counts_processing_without_attention(
    db,
) -> None:
    knowledge_repo = KnowledgeRepo(db)
    product_repo = YouzanProductRepo(db)
    history_repo = ContentChangeHistoryRepo(db)
    webhook_repo = YouzanWebhookEventRepo(db)
    webhook_id = await webhook_repo.create_received(
        YouzanWebhookEventCreate(
            msg_id="msg-processing",
            trace_id="trace-processing",
            event_type="ITEM_INFO",
            business_type="item",
            business_key="10003",
            http_status=200,
            payload_hash="hash-processing",
            payload_summary_json=json.dumps({"item_id": 10003}, ensure_ascii=False),
        )
    )
    await webhook_repo.mark_processing(
        webhook_id,
        process_stage="item_dispatched",
        business_type="item",
        business_key="10003",
    )
    service = ObservabilityService(
        knowledge_repo=knowledge_repo,
        product_repo=product_repo,
        history_repo=history_repo,
        webhook_repo=webhook_repo,
    )

    summary = await service.get_summary()

    assert summary["status"] == "ok"
    assert summary["counts"]["webhook_processing"] == 1
