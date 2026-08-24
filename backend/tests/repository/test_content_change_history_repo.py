import pytest

from app.models.content_change_history import (
    ChangeAction,
    ChangeStatus,
    ChangeEntityType,
    ContentChangeHistoryCreate,
)
from app.repository.content_change_history_repo import ContentChangeHistoryRepo


@pytest.mark.asyncio
async def test_add_and_query_content_change_history(db) -> None:
    repo = ContentChangeHistoryRepo(db)
    entry_id = await repo.add(
        ContentChangeHistoryCreate(
            entity_type=ChangeEntityType.PRODUCT,
            entity_key="10001",
            category="product",
            title="测试商品",
            source="youzan_webhook",
            action=ChangeAction.UPSERT,
            status=ChangeStatus.SUCCESS,
            change_summary_json='{"price_fen":6800}',
            occurred_at="2026-05-25 10:00:00",
        )
    )

    entry = await repo.get_by_id(entry_id)
    assert entry is not None
    assert entry.title == "测试商品"

    rows = await repo.list_entries(
        source="youzan_webhook", keyword="测试", limit=10, offset=0
    )
    assert len(rows) == 1
    assert rows[0].entity_key == "10001"

    count = await repo.count_entries(source="youzan_webhook")
    assert count == 1
