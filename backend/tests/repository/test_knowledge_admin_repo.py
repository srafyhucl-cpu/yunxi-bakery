import pytest

from app.repository.knowledge_admin_repo import KnowledgeAdminRepo
from app.repository.knowledge_repo import KnowledgeRepo


@pytest.mark.asyncio
async def test_create_admin_entry_defaults_vector_pending(db) -> None:
    repo = KnowledgeAdminRepo(db)
    knowledge_repo = KnowledgeRepo(db)
    entry_id = await repo.create_admin_entry(
        category="faq",
        content_type="faq",
        title="配送怎么收费",
        content="满额包邮，偏远地区另算。",
        keywords="配送 运费",
        priority=50,
        is_active=True,
        content_origin="admin_console",
        created_by="admin",
        updated_by="admin",
        suggested_category="faq",
        suggest_reason="疑问句更像 FAQ",
        sync_source="admin_manual",
    )

    entry = await knowledge_repo.get_by_id(entry_id)
    assert entry is not None
    assert entry.content_type == "faq"
    assert entry.vector_sync_status == "pending"
    assert entry.content_origin == "admin_console"
    assert entry.audience == "all"
    assert entry.review_status == "published"


@pytest.mark.asyncio
async def test_mark_vector_sync_status_updates_error_and_retry(db) -> None:
    admin_repo = KnowledgeAdminRepo(db)
    knowledge_repo = KnowledgeRepo(db)
    entry_id = await admin_repo.create_admin_entry(
        category="policy",
        content_type="rule",
        title="改期规则",
        content="需提前一天联系门店。",
        keywords="改期",
        priority=40,
        is_active=True,
        content_origin="admin_console",
        created_by="admin",
        updated_by="admin",
        suggested_category="rule",
        suggest_reason="规则类说明",
        sync_source="admin_manual",
    )

    await knowledge_repo.mark_vector_sync_status(
        entry_id,
        status="failed",
        error_message="向量服务不可用",
        retry_increment=True,
    )
    entry = await knowledge_repo.get_by_id(entry_id)
    assert entry is not None
    assert entry.vector_sync_status == "failed"
    assert entry.vector_sync_error == "向量服务不可用"
    assert entry.vector_sync_retry_count == 1


@pytest.mark.asyncio
async def test_create_and_update_admin_entry_keeps_governance_fields(db) -> None:
    repo = KnowledgeAdminRepo(db)
    knowledge_repo = KnowledgeRepo(db)
    entry_id = await repo.create_admin_entry(
        category="store_info",
        content_type="script",
        title="员工可复制配送话术",
        content="先确认门店排期，再回复客户。",
        keywords="配送 话术",
        priority=50,
        is_active=True,
        content_origin="admin_console",
        created_by="admin",
        updated_by="admin",
        suggested_category="script",
        suggest_reason="话术类说明",
        sync_source="admin_manual",
        audience="employee",
        review_status="draft",
        valid_from="2026-07-06 09:00:00",
        valid_until="2026-07-07 23:59:59",
        reviewed_by="ops",
        reviewed_at="2026-07-06 10:00:00",
    )

    created = await knowledge_repo.get_by_id(entry_id)
    assert created is not None
    assert created.audience == "employee"
    assert created.review_status == "draft"
    assert created.valid_from == "2026-07-06 09:00:00"
    assert created.valid_until == "2026-07-07 23:59:59"
    assert created.reviewed_by == "ops"
    assert created.reviewed_at == "2026-07-06 10:00:00"

    await repo.update_admin_entry(
        entry_id,
        category="faq",
        content_type="faq",
        title="客户配送规则",
        content="客户侧只回复已发布配送规则。",
        keywords="配送 客户",
        priority=60,
        is_active=True,
        updated_by="admin",
        suggested_category="faq",
        suggest_reason="FAQ",
        sync_source="admin_manual",
        audience="customer",
        review_status="published",
        valid_from="",
        valid_until="",
        reviewed_by="admin",
        reviewed_at="2026-07-06 11:00:00",
    )

    updated = await knowledge_repo.get_by_id(entry_id)
    assert updated is not None
    assert updated.audience == "customer"
    assert updated.review_status == "published"
    assert updated.valid_from == ""
    assert updated.valid_until == ""
    assert updated.reviewed_by == "admin"
    assert updated.reviewed_at == "2026-07-06 11:00:00"
