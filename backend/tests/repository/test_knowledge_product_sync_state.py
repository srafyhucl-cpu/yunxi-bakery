from __future__ import annotations

from app.models.content_change_history import WriteResult
from app.models.knowledge import VectorSyncStatus
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.knowledge_product_repo import KnowledgeProductRepo


async def _get_state(db, item_id: str) -> dict:
    rows = await db.execute_fetchall(
        "SELECT vector_sync_status, vector_synced_at, vector_sync_error, "
        "vector_sync_retry_count, updated_at "
        "FROM knowledge_base WHERE youzan_item_id = ?",
        (item_id,),
    )
    return rows[0]


async def test_product_vector_state_transitions_and_retry(db) -> None:
    repo = KnowledgeProductRepo(db)
    item_id = "10001"
    revision = "2026-08-07 10:00:00"

    assert (
        await repo.upsert_product_knowledge(
            item_id,
            "草莓蛋糕",
            "商品正文",
            "商品",
            0,
            revision,
        )
        == WriteResult.APPLIED
    )
    assert (await _get_state(db, item_id))["vector_sync_status"] == "pending"
    assert (await _get_state(db, item_id))["vector_synced_at"] == ""

    assert await repo.claim_product_vector_sync(item_id, revision)
    syncing_state = await _get_state(db, item_id)
    assert syncing_state["vector_sync_status"] == "syncing"
    assert syncing_state["vector_synced_at"] != ""

    assert await repo.mark_product_vector_sync_failed(
        item_id,
        revision,
        "embedding provider unavailable",
    )
    failed_state = await _get_state(db, item_id)
    assert failed_state["vector_sync_status"] == "failed"
    assert failed_state["vector_sync_error"] == "embedding provider unavailable"
    assert failed_state["vector_sync_retry_count"] == 1

    assert await repo.claim_product_vector_sync(item_id, revision)
    assert (await _get_state(db, item_id))["vector_sync_status"] == "syncing"
    assert await repo.mark_product_vector_sync_success(item_id, revision)
    success_state = await _get_state(db, item_id)
    assert success_state["vector_sync_status"] == "success"
    assert success_state["vector_synced_at"] != ""
    assert success_state["vector_sync_error"] == ""


async def test_stale_vector_worker_cannot_overwrite_newer_revision(db) -> None:
    repo = KnowledgeProductRepo(db)
    item_id = "10002"
    old_revision = "2026-08-07 10:00:00"
    new_revision = "2026-08-07 11:00:00"

    await repo.upsert_product_knowledge(
        item_id,
        "旧商品",
        "旧正文",
        "旧关键词",
        0,
        old_revision,
    )
    assert await repo.claim_product_vector_sync(item_id, old_revision)

    await repo.upsert_product_knowledge(
        item_id,
        "新商品",
        "新正文",
        "新关键词",
        0,
        new_revision,
    )

    assert not await repo.mark_product_vector_sync_success(item_id, old_revision)
    state = await _get_state(db, item_id)
    assert state["vector_sync_status"] == "pending"
    assert state["updated_at"] == new_revision


async def test_product_vector_failure_truncates_error_text(db) -> None:
    repo = KnowledgeProductRepo(db)
    item_id = "10003"
    revision = "2026-08-07 12:00:00"
    long_error = "x" * 800

    await repo.upsert_product_knowledge(
        item_id,
        "商品",
        "正文",
        "关键词",
        0,
        revision,
    )
    assert await repo.claim_product_vector_sync(item_id, revision)
    assert await repo.mark_product_vector_sync_failed(item_id, revision, long_error)

    state = await _get_state(db, item_id)
    assert len(state["vector_sync_error"]) == 500


async def test_generic_knowledge_sync_does_not_claim_product_rows(db) -> None:
    product_repo = KnowledgeProductRepo(db)
    await product_repo.upsert_product_knowledge(
        "10004",
        "商品",
        "正文",
        "关键词",
        0,
        "2026-08-07 12:00:00",
    )
    knowledge_repo = KnowledgeRepo(db)

    pending_entries = await knowledge_repo.get_pending_sync_entries()

    assert pending_entries == []
    assert VectorSyncStatus.PENDING.value == "pending"
